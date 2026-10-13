# ============================================
# FILE: tts_audio.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Text-to-speech (TTS) and playback of the call sound.

  - Generates a spoken sentence (e.g. "Hey grandma, it's XXX calling")
    with gTTS (Google Text-to-Speech), in the language set in config.py.
  - Mixes this voice with the background ringtone using ffmpeg
    (voice and ringtone looped over the whole call duration).
  - Caches the final result (one file per caller name and language).
  - Plays the result with 'aplay' in a subprocess, which can be stopped
    (terminate) through the AlertSound class.
  - Finds the sound card for the ringtone at every call (USB speaker
    detected automatically, see config.AUDIO_DEVICE).
"""

import glob
import os
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


def set_max_volume(card):
    """
    Sets the volume of the card to 100 %, trying the usual control names.
    Does nothing for the default output (its volume is the system's).
    """
    if card is None:
        return
    for control in VOLUME_CONTROLS:
        result = subprocess.run(
            ["amixer", "-c", card["id"], "sset", control, "100%"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return
    print(f"⚠️ Could not set the volume of '{card['id']}' (no {'/'.join(VOLUME_CONTROLS)} control)")


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

    # The language is part of the file name: changing LANGUAGE must not
    # replay an announcement cached in the previous language.
    final_wav = config.CACHE_DIR / f"call_{lang}_{file_key}.wav"

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

    phrase = t("tts.phrase", name=display_name)

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
