# Tests the ringtone of the real tts_audio.py: sound card selection, with a
# simulated /proc/asound/cards, and ringtone repeated over the whole call when
# there is no voice announcement. aplay, amixer and ffmpeg are simulated.
import subprocess
import tempfile
import sys
import types
from pathlib import Path

P = Path(tempfile.mkdtemp())
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Raspberry_receiver/

cfg = types.ModuleType("config")
cfg.LANGUAGE = "fr"
cfg.BASE_DIR = P
cfg.CACHE_DIR = P / "cache"
cfg.CACHE_DIR.mkdir()
cfg.AUDIO_DEVICE = None
cfg.RINGTONE_PATH = str(P / "ringtone.wav")
(P / "ringtone.wav").write_bytes(b"RIFF ringtone")
cfg.CALL_DURATION = 30; cfg.MAX_CACHED_CALLS = 30; cfg.MAX_CALLER_NAME_LENGTH = 30
cfg.VOICE_VOLUME = 1.5; cfg.RINGTONE_VOLUME = 0.2
sys.modules["config"] = cfg

import tts_audio  # noqa: E402

import shutil
ASOUND = P / "asound"
CARDS_FILE = ASOUND / "cards"
tts_audio.ASOUND_DIR = str(ASOUND)
tts_audio.ASOUND_CARDS_FILE = str(CARDS_FILE)


def set_cards(text, capture_only=()):
    """Simulated /proc/asound: cards file + cardN/pcm0p (or pcm0c) folders."""
    shutil.rmtree(ASOUND, ignore_errors=True)
    ASOUND.mkdir(parents=True)
    CARDS_FILE.write_text(text)
    for line in text.splitlines():
        m = tts_audio.CARD_LINE.match(line)
        if m:
            stream = "pcm0c" if m.group(2) in capture_only else "pcm0p"
            (ASOUND / f"card{m.group(1)}" / stream).mkdir(parents=True)
tts_audio.gTTS = None  # no network: raw ringtone

HDMI_ONLY = """ 0 [vc4hdmi0       ]: vc4-hdmi - vc4-hdmi-0
                      vc4-hdmi-0
 1 [vc4hdmi1       ]: vc4-hdmi - vc4-hdmi-1
                      vc4-hdmi-1
"""
WITH_USB = HDMI_ONLY + """ 2 [AUDIO          ]: USB-Audio - USB Audio
                      Generic USB Audio at usb-0000:01:00.0-1.2, full speed
"""
OTHER_MODEL = HDMI_ONLY + """ 3 [Speaker        ]: USB-Audio - Jabra SPEAK 410 USB
                      Jabra SPEAK 410 USB at usb-0000:01:00.0-1.4, full speed
"""

# --- Simulated commands ---
calls = []
played_files = []              # file given to aplay at each call
ffmpeg_fails = []              # [True]: ffmpeg stops with an error
amixer_ok_controls = {"PCM"}   # controls accepted by the simulated card
aplay_fails_on = set()          # devices on which aplay stops at once with an error


class FakeProcess:
    def __init__(self, args, **kwargs):
        calls.append(("aplay", args[2]))
        played_files.append(args[3])
        self.fails = args[2] in aplay_fails_on

    def wait(self, timeout=None):
        if self.fails:
            return 1
        raise subprocess.TimeoutExpired("aplay", timeout)

    def terminate(self):
        pass


def fake_run(args, **kwargs):
    if args[0] == "ffmpeg":
        calls.append(("ffmpeg", args))
        if ffmpeg_fails:
            raise subprocess.CalledProcessError(1, args)
        Path(args[-1]).write_bytes(b"RIFF looped")
        return types.SimpleNamespace(returncode=0)
    calls.append(("amixer", args[2], args[4]))
    return types.SimpleNamespace(returncode=0 if args[4] in amixer_ok_controls else 1)


tts_audio.subprocess.Popen = FakeProcess
tts_audio.subprocess.run = fake_run

results = []


def check(name, condition, detail=""):
    results.append(condition)
    print(("✅ " if condition else "❌ ") + name + (f"  → {detail}" if detail else ""))


def ring():
    calls.clear()
    sound = tts_audio.AlertSound()
    sound.play("Paul")
    sound.stop()
    return [c[1] for c in calls if c[0] == "aplay"], [c for c in calls if c[0] == "amixer"]


# 1. Usual setup: HDMI outputs + USB speaker named AUDIO
set_cards(WITH_USB)
played, mixer = ring()
check("current USB speaker (AUDIO): ringtone on it", played == ["plughw:CARD=AUDIO,DEV=0"], played)
check("volume set on the USB speaker", mixer[:1] == [("amixer", "AUDIO", "PCM")], mixer)

# 2. Another USB speaker model, on another port (another card number)
set_cards(OTHER_MODEL)
played, _ = ring()
check("other USB speaker model: found automatically", played == ["plughw:CARD=Speaker,DEV=0"], played)

# 3. Volume control with another name
amixer_ok_controls.clear(); amixer_ok_controls.add("Speaker")
played, mixer = ring()
check("volume control with another name (Speaker): found",
      [m[2] for m in mixer] == ["PCM", "Speaker"], [m[2] for m in mixer])
amixer_ok_controls.clear(); amixer_ok_controls.add("PCM")

# 4. No USB speaker: ringtone on the default output, no volume command
set_cards(HDMI_ONLY)
played, mixer = ring()
check("no USB speaker: ringtone on the default output (HDMI)", played == ["default"], played)
check("no volume setting on the default output", mixer == [], mixer)

# 5. Speaker plugged back in between two calls
set_cards(WITH_USB)
played, _ = ring()
check("speaker plugged back in between two calls: found again", played == ["plughw:CARD=AUDIO,DEV=0"], played)

# 6. Card refuses to play: immediate fallback to the default output
aplay_fails_on.add("plughw:CARD=AUDIO,DEV=0")
played, _ = ring()
check("speaker refuses to play: fallback to the default output",
      played == ["plughw:CARD=AUDIO,DEV=0", "default"], played)
aplay_fails_on.clear()

# 7. Forced card (AUDIO_DEVICE) present, even if another USB card comes first
cfg.AUDIO_DEVICE = "AUDIO"
set_cards(OTHER_MODEL + WITH_USB.split("vc4-hdmi-1\n", 1)[1])
played, _ = ring()
check("forced card present: used (not the other USB speaker)", played == ["plughw:CARD=AUDIO,DEV=0"], played)

# 8. Forced card absent
set_cards(OTHER_MODEL)
played, _ = ring()
check("forced card absent: default output (not another speaker)", played == ["default"], played)
cfg.AUDIO_DEVICE = None

# 9. Real Pi: USB webcam (microphone only) BEFORE the USB speaker
PI = HDMI_ONLY + """ 2 [Headphones     ]: bcm2835_headpho - bcm2835 Headphones
                      bcm2835 Headphones
 3 [Webcam         ]: USB-Audio - Trust 1080p Full HD Webcam
                      BC-240717-PZJ Trust 1080p Full HD Webcam at usb-0000:01:00.0-1.2, high speed
 4 [AUDIO          ]: USB-Audio - USB  AUDIO
                      USB  AUDIO at usb-0000:01:00.0-1.1, full speed
"""
set_cards(PI, capture_only=("Webcam",))
played, mixer = ring()
check("webcam (microphone only) ignored: ringtone on the AUDIO speaker", played == ["plughw:CARD=AUDIO,DEV=0"], played)
check("volume set on the speaker, not on the webcam", mixer[:1] == [("amixer", "AUDIO", "PCM")], mixer)

# 10. Only the webcam (speaker unplugged): default output, not the webcam
set_cards(PI.split(" 4 [AUDIO")[0], capture_only=("Webcam",))
played, _ = ring()
check("webcam only (speaker unplugged): default output", played == ["default"], played)

# 11. Card list unreadable (not a Linux system, etc.)
CARDS_FILE.unlink()
played, _ = ring()
check("card list unreadable: default output", played == ["default"], played)

# 12. No voice announcement: the ringtone (a few seconds) repeated over the call
set_cards(WITH_USB)
for f in (P / "cache").glob("ringtone_*.wav"):  # made by the calls above
    f.unlink()
played_files.clear()
played, _ = ring()
ffmpeg = [c[1] for c in calls if c[0] == "ffmpeg"]
looped = str(P / "cache" / "ringtone_ringtone_30s.wav")
check("no announcement: ringtone repeated over the 30 s of the call (ffmpeg)",
      ffmpeg == [["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(P / "ringtone.wav"), "-t", "30", looped]], ffmpeg)
check("... and that file is played", played_files == [looped], played_files)
played_files.clear()
ring()
check("next call: repeated ringtone taken from the cache (no ffmpeg)",
      not [c for c in calls if c[0] == "ffmpeg"] and played_files == [looped], played_files)

# 13. Ringtone changed: the repeated version is made again
import os, time
later = time.time() + 60
os.utime(P / "ringtone.wav", (later, later))
ring()
check("ringtone file changed: repeated version made again", [c for c in calls if c[0] == "ffmpeg"] != [])

# 14. ffmpeg fails: the ringtone is played once rather than nothing
for f in (P / "cache").glob("ringtone_*.wav"):
    f.unlink()
ffmpeg_fails.append(True)
played_files.clear()
ring()
check("ffmpeg fails: the ringtone is played once", played_files == [str(P / "ringtone.wav")], played_files)
ffmpeg_fails.clear()

# 15. Ringtone of one's own (RINGTONE_PATH) deleted: the project ringtone is used
cfg.RINGTONE_PATH = str(P / "my-ringtone.wav")
played_files.clear()
ring()
ffmpeg = [c[1] for c in calls if c[0] == "ffmpeg"]
check("RINGTONE_PATH file missing: the project ringtone is used (never silent)",
      ffmpeg and ffmpeg[0][5] == str(P / "ringtone.wav"), ffmpeg)
(P / "my-ringtone.wav").write_bytes(b"RIFF mine")
played_files.clear()
ring()
check("RINGTONE_PATH file present: that ringtone is used",
      played_files == [str(P / "cache" / "ringtone_my-ringtone_30s.wav")], played_files)

print(f"\n{sum(results)} passed, {len(results) - sum(results)} failed")
sys.exit(0 if all(results) else 1)
