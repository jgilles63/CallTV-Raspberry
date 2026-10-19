# ============================================
# FILE: tts_audio.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Text-to-speech (TTS) and playback of the call sound.

  - Generates a spoken sentence (e.g. "Hey grandma, it's XXX calling", the
    greeting being config.GREETING_NAME) with gTTS (Google Text-to-Speech), in
    the language set in config.py.
  - Mixes this voice with the background ringtone using ffmpeg
    (voice and ringtone looped over the whole call duration).
  - Caches the final result (one file per caller name and language).
  - Plays the result with 'aplay' in a subprocess, which can be stopped
    (terminate) through the AlertSound class.
  - Finds the sound card for the ringtone at every call (USB speaker
    detected automatically, see config.AUDIO_DEVICE).
  - Says the answers of the robot to the spoken commands (say: one sentence
    of i18n.py, cached, on the same speaker).
  - Two volumes of the speaker (decision of 19/10/2026: a quiet radio must
    never make the robot hard to hear): the radio, 0 to 100 % in
    radio_volume.txt (20 % at first; slider of the radio page, settings
    page, "Robot, volume 5" while it plays = 50 %), and the voice of the
    robot, level 1 to 10 in voice_volume.txt (8 at first; settings page,
    "Robot, volume 5" when the radio is off). The ringtone is always at
    100 % (it must be heard).
"""

import glob
import hashlib
import os
import wave
import re
import subprocess

import config
from i18n import language, t

try:
    from gtts import gTTS
except ImportError:
    print("⚠️ gTTS is not installed. Install it with: pip install gtts")
    gTTS = None


# ---------------------------------------------------------
# Sound card of the ringtone
# ---------------------------------------------------------

# List of the sound cards known by ALSA
ASOUND_DIR = "/proc/asound"
ASOUND_CARDS_FILE = ASOUND_DIR + "/cards"

# A line of /proc/asound/cards looks like:
#  1 [AUDIO          ]: USB-Audio - USB Audio Device
CARD_LINE = re.compile(r"^\s*(\d+)\s+\[(\S+)\s*\]:\s+(\S+)\s+-\s+(.*)$")

# Volume controls tried in this order (their name depends on the card model)
VOLUME_CONTROLS = ("PCM", "Speaker", "Master", "Headphone")
# Volume of the radio (0 to 100 %) and of the voice of the robot (level 1 to
# 10 = 10 % to 100 %), kept in these files of the application folder;
# speaker_volume.txt: volume of the radio before 19/10/2026 (a level), read
# once if radio_volume.txt does not exist yet
RADIO_VOLUME_FILE_NAME = "radio_volume.txt"
OLD_VOLUME_FILE_NAME = "speaker_volume.txt"
VOICE_VOLUME_FILE_NAME = "voice_volume.txt"
VOLUME_LEVELS = range(1, 11)
# Never set: these volumes
DEFAULT_RADIO_VOLUME = 20
DEFAULT_VOICE_LEVEL = 8
# Voice of the robot in its WAV files (its loudness then follows the volume
# said by voice); VOICE_VOLUME is the voice of the announcement of a call
ROBOT_VOICE_VOLUME = 1.5


def list_sound_cards():
    """
    Returns the sound cards as a list of dicts {index, id, driver, name,
    playback}, or an empty list if they cannot be read.
    playback is False for capture-only cards (e.g. the microphone of a USB
    webcam): they have no /proc/asound/cardN/pcm*p (playback) stream.
    """
    try:
        with open(ASOUND_CARDS_FILE, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return []

    cards = []
    for line in lines:
        match = CARD_LINE.match(line)
        if match:
            index, card_id, driver, name = match.groups()
            playback = bool(glob.glob(f"{ASOUND_DIR}/card{index}/pcm*p"))
            cards.append({"index": int(index), "id": card_id, "driver": driver,
                          "name": name.strip(), "playback": playback})
    return cards


def find_ringing_card():
    """
    Returns the card used for the ringtone, or None to use the default output.

    - config.AUDIO_DEVICE set: that card, if it is plugged in.
    - config.AUDIO_DEVICE = None: the first USB sound card that can play
      sound (a webcam microphone is skipped).
    A warning is printed when falling back to the default output.
    """
    cards = list_sound_cards()
    wanted = getattr(config, "AUDIO_DEVICE", None)

    if wanted:
        for card in cards:
            if card["id"] == wanted:
                return card
        print(f"⚠️ Sound card '{wanted}' not found, ringing on the default output (HDMI)")
        return None

    for card in cards:
        if card["driver"] == "USB-Audio" and card["playback"]:
            return card
    print("⚠️ No USB speaker found, ringing on the default output (HDMI)")
    return None


def playback_device(card):
    """ALSA device given to aplay for this card (default output if None)."""
    return f"plughw:CARD={card['id']},DEV=0" if card else "default"


def set_card_volume(card, percent, mapped=False):
    """
    Sets the volume of the card (percent), trying the usual control names;
    mapped: on the scale of the ear (amixer -M), for the levels said by
    voice. Does nothing for the default output (its volume is the system's).
    """
    if card is None:
        return
    for control in VOLUME_CONTROLS:
        result = subprocess.run(
            ["amixer"] + (["-M"] if mapped else []) + ["-c", card["id"], "sset", control, f"{int(percent)}%"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return
    print(f"⚠️ Could not set the volume of '{card['id']}' (no {'/'.join(VOLUME_CONTROLS)} control)")


def set_max_volume(card):
    """Sets the volume of the card to 100 % (the ringtone)."""
    set_card_volume(card, 100)


def read_level(path, default, levels=VOLUME_LEVELS):
    try:
        level = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError, AttributeError):
        return default
    return level if level in levels else default


def write_level(path, level, levels=VOLUME_LEVELS):
    """Keeps a volume; False if not valid or not saved."""
    if isinstance(level, bool) or level not in levels:
        return False
    try:
        path.write_text(f"{level}\n", encoding="utf-8")
    except OSError as e:
        print(f"⚠️ Volume not saved ({e})")
        return False
    return True


def radio_volume():
    """Volume of the radio, 0 to 100 % (DEFAULT_RADIO_VOLUME if never set)."""
    volume = read_level(config.BASE_DIR / RADIO_VOLUME_FILE_NAME, None, range(0, 101))
    if volume is None:
        old_level = read_level(config.BASE_DIR / OLD_VOLUME_FILE_NAME, None)
        volume = old_level * 10 if old_level else DEFAULT_RADIO_VOLUME
    return volume


def save_radio_volume(percent):
    """Keeps the volume of the radio (0 to 100 %); False if not valid or not saved."""
    return write_level(config.BASE_DIR / RADIO_VOLUME_FILE_NAME, percent, range(0, 101))


def voice_level():
    """Volume of the voice of the robot, 1 to 10 (DEFAULT_VOICE_LEVEL if never set)."""
    return read_level(config.BASE_DIR / VOICE_VOLUME_FILE_NAME, DEFAULT_VOICE_LEVEL)


def save_voice_level(level):
    """Keeps the volume of the voice of the robot (1 to 10); False if not valid or not saved."""
    return write_level(config.BASE_DIR / VOICE_VOLUME_FILE_NAME, level)


def set_speaker_volume(percent=None):
    """
    Volume of the speaker for the radio: its volume, or percent (the radio
    turned down while the robot listens).
    """
    set_card_volume(find_ringing_card(), radio_volume() if percent is None else percent, mapped=True)


def clean_greeting():
    """
    Greeting of the announcement (config.GREETING_NAME), cleaned like a
    caller name; "" if there is none.
    """
    greeting = getattr(config, "GREETING_NAME", None)
    if not greeting or not isinstance(greeting, str):
        return ""
    greeting = greeting.strip()[:config.MAX_CALLER_NAME_LENGTH]
    return "".join(c for c in greeting if c.isalnum() or c in " -'").strip()


def call_phrase(display_name):
    """Sentence of the announcement, with or without greeting."""
    greeting = clean_greeting()
    if greeting:
        return t("tts.phrase", name=display_name, greeting=greeting)
    return t("tts.phraseNoGreeting", name=display_name)


def clean_name_for_tts(name):
    """
    Cleans the caller name so it can be spoken, without special
    characters that could be dangerous for the TTS.
    Returns "someone" (translated) if the name is empty/invalid.
    """
    if not name:
        return t("tts.someone")
    name = name.strip()[:config.MAX_CALLER_NAME_LENGTH]
    name = "".join(c for c in name if c.isalnum() or c in " -'")
    return name if name else t("tts.someone")


def safe_filename_from_name(name):
    """
    Turns a cleaned name into a safe file name key (lowercase,
    without spaces or dashes) used for the cache.
    """
    name = clean_name_for_tts(name)
    return name.lower().replace(" ", "").replace("-", "")


def prune_audio_cache():
    """
    Limits the cache size: keeps at most config.MAX_CACHED_CALLS - 1
    files (room for the new one), deleting the least recently used.
    Prevents a series of calls with different names from filling the
    SD card.
    """
    cached = sorted(
        config.CACHE_DIR.glob("call_*.wav"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    for old_file in cached[config.MAX_CACHED_CALLS - 1:]:
        try:
            old_file.unlink()
            print(f"🧹 Audio cache: deleting {old_file.name}")
        except OSError as e:
            print(f"⚠️ Cannot delete {old_file}: {e}")


def ringtone_path():
    """
    WAV file of the ringtone: config.RINGTONE_PATH, or the ringtone of the
    project if that file is missing (a call must never stay silent).
    """
    default = str(config.BASE_DIR / "ringtone.wav")
    if not os.path.exists(config.RINGTONE_PATH) and os.path.exists(default):
        print(f"⚠️ Ringtone {config.RINGTONE_PATH} not found, using {default}")
        return default
    return config.RINGTONE_PATH


def looped_ringtone():
    """
    Ringtone repeated over the whole call duration (cached), played when
    there is no voice announcement: aplay plays a file only once, and the
    ringtone lasts only a few seconds. Returns the ringtone itself (played
    once) if ffmpeg fails.
    """
    source = ringtone_path()
    stem = os.path.splitext(os.path.basename(source))[0]
    looped = config.CACHE_DIR / f"ringtone_{stem}_{config.CALL_DURATION}s.wav"
    try:
        if not looped.exists() or os.path.getmtime(source) > looped.stat().st_mtime:
            subprocess.run(
                ["ffmpeg", "-y", "-stream_loop", "-1", "-i", source,
                 "-t", str(config.CALL_DURATION), str(looped)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        return str(looped)
    except Exception as e:
        print(f"⚠️ Looped ringtone not made ({e}), playing it once")
        return source


def generate_call_wav(caller_name):
    """
    Generates (or gets from the cache) the final WAV = TTS voice mixed
    with the background ringtone, for a given caller.

    Returns the path of the final WAV file, or None on failure
    (for example if gTTS is not installed).
    """
    lang = language()
    display_name = clean_name_for_tts(caller_name)
    file_key = safe_filename_from_name(caller_name)
    greeting_key = clean_greeting().lower().replace(" ", "").replace("-", "").replace("'", "") or "none"

    # The language, the greeting and the volumes of the music and the voice
    # are part of the file name: changing LANGUAGE, GREETING_NAME,
    # RINGTONE_VOLUME or VOICE_VOLUME (settings page) must not replay an older
    # announcement.
    ringtone_key = f"r{round(float(config.RINGTONE_VOLUME) * 100)}v{round(float(config.VOICE_VOLUME) * 100)}"
    final_wav = config.CACHE_DIR / f"call_{lang}_{greeting_key}_{ringtone_key}_{file_key}.wav"

    # --- Cache: already generated for this name, reuse it directly ---
    if final_wav.exists():
        print(f"✅ Cache found for '{display_name}': {final_wav}")
        # Mark the file as recently used (see prune_audio_cache)
        final_wav.touch()
        return str(final_wav)

    if not gTTS:
        print("⚠️ gTTS not available, falling back to the raw ringtone")
        return None

    prune_audio_cache()

    phrase = call_phrase(display_name)

    voice_mp3 = config.CACHE_DIR / f"voice_{lang}_{file_key}.mp3"
    voice_wav = config.CACHE_DIR / f"voice_{lang}_{file_key}.wav"

    try:
        # --- 1. Generate the TTS voice (mp3) ---
        print(f"🔊 TTS generation: '{phrase}'")
        tts = gTTS(text=phrase, lang=lang)
        tts.save(str(voice_mp3))

        # --- 2. Convert mp3 -> wav (ffmpeg) ---
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(voice_mp3), str(voice_wav)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        # --- 3. Mix the voice (looped) + ringtone (looped) over the call duration ---
        filter_complex = (
            f"[0:a]aloop=loop=-1:size=2e9,atrim=0:{config.CALL_DURATION},dynaudnorm,volume={config.VOICE_VOLUME}[voice];"
            f"[1:a]aloop=loop=-1:size=2e9,atrim=0:{config.CALL_DURATION},volume={config.RINGTONE_VOLUME}[ring];"
            f"[voice][ring]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[out]"
        )

        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(voice_wav),
            "-i", ringtone_path(),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            str(final_wav)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        print(f"✅ Generated and cached: {final_wav}")
        return str(final_wav)

    except Exception as e:
        print(f"❌ TTS generation error ({e})")
        return None
    finally:
        # --- Clean up the temporary files (voice only, before mixing) ---
        for f in (voice_mp3, voice_wav):
            if f.exists():
                f.unlink()


def make_speech_wav(text, wav):
    """Generates the spoken text into the WAV file wav (gTTS + ffmpeg); True if done."""
    if not gTTS:
        return False
    mp3 = wav.with_suffix(".mp3")
    try:
        gTTS(text=text, lang=language()).save(str(mp3))
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(mp3), "-af", f"dynaudnorm,volume={ROBOT_VOICE_VOLUME}", str(wav)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        print(f"❌ Sentence of the robot not generated ({e})")
        return False
    finally:
        if mp3.exists():
            mp3.unlink()


def spoken_wav(key):
    """
    WAV file of a fixed sentence of the robot (i18n key, e.g. "voice.hello")
    in the language of the Raspberry, generated once then cached; None on
    failure.
    """
    lang = language()
    text = t(key)
    # The text is part of the name: a changed sentence is generated again
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    wav = config.CACHE_DIR / f"say_{lang}_{re.sub(r'[^a-z0-9]+', '_', key.lower())}_{digest}.wav"
    if wav.exists():
        return str(wav)
    return str(wav) if make_speech_wav(text, wav) else None


def text_wav(text):
    """
    WAV file of a sentence that changes every time (the time, the weather):
    not cached, the same file is used again at each answer. None on failure.
    """
    wav = config.CACHE_DIR / "say_now.wav"
    return str(wav) if make_speech_wav(text, wav) else None


def wav_seconds(path):
    """Length of a WAV file in seconds (0 if unknown)."""
    try:
        with wave.open(str(path), "rb") as f:
            return f.getnframes() / float(f.getframerate() or 1)
    except (OSError, EOFError, wave.Error):
        return 0


def play_wav(wav):
    """
    Plays a sentence of the robot on the speaker of the ringtone and returns
    when it is over. False if it could not be played.
    """
    if not wav:
        return False
    card = find_ringing_card()
    set_card_volume(card, voice_level() * 10, mapped=True)
    try:
        result = subprocess.run(["aplay", "-q", "-D", playback_device(card), wav],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"⚠️ Sentence of the robot not played ({e})")
        return False
    return result.returncode == 0


def say(key):
    """
    Says a fixed sentence of the robot (i18n key) and returns when it is
    over. False if it could not be said (no internet the first time, no
    speaker...).
    """
    return play_wav(spoken_wav(key))


class AlertSound:
    """
    Manages the audio playback process (aplay) of the call ringtone.
    Only one sound can be played at a time (self.process).
    """

    def __init__(self):
        self.process = None

    def play(self, caller_name=None):
        """
        Starts playing the call sound.
        If a caller_name is given, tries to generate/get the mixed
        TTS + ringtone WAV; otherwise (or on failure), plays the raw ringtone.
        """
        if self.process is not None:
            # A sound is already playing: do not start another one.
            return

        # Sound card searched at every call: a speaker unplugged and plugged
        # back in (any USB port) is found again.
        card = find_ringing_card()
        set_max_volume(card)

        wav_path = None

        if caller_name:
            generated_path = generate_call_wav(caller_name)
            if generated_path and os.path.exists(generated_path):
                wav_path = generated_path
            else:
                print("⚠️ TTS generation failed, falling back to the raw ringtone")
        if wav_path is None:
            wav_path = looped_ringtone()

        where = f"{card['name']} ({card['id']})" if card else "default output"
        print(f"🔊 Playing the call sound on {where}: {wav_path}")
        self.process = subprocess.Popen(["aplay", "-D", playback_device(card), wav_path])

        # If the card refuses to play (unplugged meanwhile, busy...), aplay
        # stops at once: ring on the default output rather than not at all.
        if card is not None:
            try:
                exit_code = self.process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                return  # still playing: all good
            if exit_code != 0:
                print(f"⚠️ Playback failed on '{card['id']}', ringing on the default output (HDMI)")
                self.process = subprocess.Popen(["aplay", "-D", "default", wav_path])

    def stop(self):
        """Stops the current playback, if any."""
        if self.process is not None:
            print("⏹️ Stopping the call sound")
            self.process.terminate()
            self.process = None
