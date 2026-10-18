# Sound near the TV (sound_level.py and agent.py, ROADMAP 2.13 level 1): only
# the volume of the microphone is measured, the robot of the TV page reacts.
# Volumes from a real Pi on 17/10/2026 (camera microphone, quiet living room:
# about 400 of 32767 after a loud first second). Checks: volume of the
# samples, first second ignored, a voice detected (start / end), short noises
# ignored, threshold that follows the background noise (a TV left loud stops
# being "a sound"), "a sound starts" said again during a long sound; reading
# pw-record (simulated), stop when it should not listen, pw-record missing,
# VOICE_REACTION = False; agent: only outside calls, sound_activity sent.
import array
import asyncio
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Raspberry_receiver/

cfg = types.ModuleType("config")
cfg.LANGUAGE = "fr"; cfg.RASPBERRY_ID = "rpi-sound"; cfg.DEVICE_SECRET = "secret"
cfg.SERVER_URL = "wss://x"; cfg.UNAUTHORIZED_RETRY_DELAY = 30; cfg.CALL_DURATION = 30
cfg.MOUSE_DEVICE = None; cfg.MOUSE_RETRY_DELAY = 5; cfg.BASE_DIR = Path(tempfile.mkdtemp())
sys.modules["config"] = cfg

evdev = types.ModuleType("evdev")
evdev.InputDevice = object
evdev.list_devices = lambda: []
evdev.ecodes = types.SimpleNamespace(EV_KEY=1, KEY={}, BTN_LEFT=272, REL_X=0, EV_REL=2)
sys.modules["evdev"] = evdev

tv = types.ModuleType("tv_control")
tv.tv_on_and_accept = lambda: None
tv.tv_return = lambda: None
sys.modules["tv_control"] = tv


class FakeSound:
    def play(self, name):
        pass

    def stop(self):
        pass


audio = types.ModuleType("tts_audio")
audio.AlertSound = FakeSound
sys.modules["tts_audio"] = audio

import sound_level as s  # noqa: E402
import agent  # noqa: E402

passed = failed = 0


def check(label, condition, detail=""):
    global passed, failed
    passed, failed = passed + bool(condition), failed + (not condition)
    print(f"{'OK ' if condition else 'KO '} {label} {detail}")


def frame(amplitude):
    """100 ms of samples whose volume is amplitude (+a, -a, ...)."""
    return array.array("h", [amplitude, -amplitude] * (s.FRAME_SAMPLES // 2)).tobytes()


def changes(volumes):
    detector = s.SoundDetector()
    return [(i, c) for i, c in enumerate(detector.feed(v) for v in volumes) if c is not None]


SECOND = 10  # frames

# --- Volume ---
check("volume of a frame: its amplitude", s.level(frame(1000)) == 1000 and s.level(frame(0)) == 0)
check("empty or odd data: no crash", s.level(b"") == 0 and s.level(b"\x01") == 0)

# --- Detection ---
quiet = [400] * (2 * SECOND)
start = [5000, 1600, 900] + [500] * 7  # first second of the real microphone
voice = [3000] * SECOND
found = changes(start + quiet + voice + quiet)
check("voice of 1 s in a quiet room: starts after 300 ms, ends after 1.5 s of quiet",
      found == [(10 + 20 + 2, True), (10 + 20 + 10 + 14, False)], found)
check("loud first second of the microphone: ignored", changes(start + quiet) == [])
check("short noise (200 ms: a cough, a door): ignored", changes(start + quiet + [6000, 6000] + quiet) == [])
check("pauses between words (< 1.5 s): one single sound",
      [c for _, c in changes(start + quiet + voice + [400] * 8 + voice + quiet)] == [True, False])
check("small noises below 600 are not \"a sound\" (minimum level)", changes(start + quiet + [580] * (5 * SECOND)) == [])
noisy = [1000] * (5 * SECOND)
check("noisy room (1000): its noise is not a sound, a voice above it is",
      [c for _, c in changes(start + noisy + [6000] * SECOND + noisy)] == [True, False])
far_voice = [450] * SECOND  # "robot" said from the sofa, in a big room (quiet: 150)
far_quiet = [150] * (2 * SECOND)
check("voice far from the microphone (450): the robot does not walk", changes(start + far_quiet + far_voice + far_quiet) == [])
voice_detector = s.SoundDetector(s.VOICE_RATIO, s.VOICE_MIN_LEVEL, s.VOICE_START_FRAMES)
heard = [(i, c) for i, c in enumerate(voice_detector.feed(v) for v in start + far_quiet + far_voice + far_quiet) if c is not None]
check("... but the spoken commands listen to it (more sensitive, after 200 ms)", heard and heard[0] == (10 + 20 + 1, True), heard)
tv_loud = changes(start + quiet + [2500] * (300 * SECOND) + quiet)
check("TV left loud for 5 minutes: a sound at first, the background noise after about 10 s",
      [c for _, c in tv_loud] == [True, False] and 5 * SECOND < tv_loud[1][0] - tv_loud[0][0] < 30 * SECOND, tv_loud)


# --- Reading the microphone (pw-record simulated) ---
def fake_record(volumes, then_forever=None):
    """Command writing these volumes (100 ms each), then the last one forever if asked."""
    data = b"".join(frame(v) for v in volumes)
    path = Path(tempfile.mkdtemp(), "mic.raw")
    path.write_bytes(data)
    forever = f"""
import time
while True:
    sys.stdout.buffer.write({frame(then_forever)!r}); sys.stdout.buffer.flush(); time.sleep(0.01)
""" if then_forever else ""
    script = f"import sys\nsys.stdout.buffer.write(open({str(path)!r}, 'rb').read()); sys.stdout.buffer.flush()\n{forever}"
    return [sys.executable, "-c", script]


async def reading():
    got = []

    async def on_change(active):
        got.append(active)

    s.RECORD_COMMAND = fake_record(start + quiet + voice + quiet)
    stopped_on_purpose = await s.listen_once(on_change, lambda: True)
    check("pw-record read: voice start and end told", got == [True, False], got)
    check("pw-record ended by itself: told as a failure (tried again later)", stopped_on_purpose is False)

    got.clear()
    s.RECORD_COMMAND = fake_record(start + quiet, then_forever=3000)
    listening = {"on": True}

    async def on_change_stop(active):
        got.append(active)
        if active:
            listening["on"] = False  # a call comes

    stopped_on_purpose = await asyncio.wait_for(s.listen_once(on_change_stop, lambda: listening["on"]), 10)
    check("should not listen any more (a call): pw-record stopped, end of the sound told",
          stopped_on_purpose is True and got == [True, False], got)

    got.clear()
    s.RECORD_COMMAND = fake_record(start + quiet, then_forever=3000)
    keepalive, s.KEEPALIVE_SECONDS = s.KEEPALIVE_SECONDS, 0.2
    async def counting(active):
        got.append(active)

    def until_four():
        return got.count(True) < 4

    await asyncio.wait_for(s.listen_once(counting, until_four), 10)
    s.KEEPALIVE_SECONDS = keepalive
    check("long sound: \"a sound starts\" said again regularly (the page forgets it otherwise)",
          got.count(True) == 4 and got[-1] is False, got)

    got.clear()
    s.RECORD_COMMAND = ["pw-record-missing-for-the-test"]
    task = asyncio.create_task(s.listen(on_change, lambda: True, retry_delay=0.05, idle_delay=0.01))
    await asyncio.sleep(0.3)
    check("pw-record missing (no PipeWire): no crash, nothing told, tried again", not task.done() and got == [])
    task.cancel()

    cfg.VOICE_REACTION = False
    s.RECORD_COMMAND = fake_record(start + quiet + voice + quiet)
    task = asyncio.create_task(s.listen(on_change, lambda: True, retry_delay=0.05, idle_delay=0.01))
    await asyncio.sleep(0.5)
    check("VOICE_REACTION = False: microphone never read", got == [])
    task.cancel()
    del cfg.VOICE_REACTION


async def agent_behaviour():
    a = agent.TVControlAgent()
    sent = []

    async def capture(data):
        sent.append(data)

    a.send_message = capture
    check("not connected to the server: not listened to", a.should_listen_sound() is False)
    a.registered = True
    check("connected, outside calls: listened to", a.should_listen_sound() is True)
    a.call_window, a.current_call_id = True, "c0"
    check("while it rings: listened to (\"Robot, décroche\")", a.should_listen_sound() is True)
    a.call_window, a.current_call_id = False, None
    for state in ({"active_call_id": "c1"}, {"outgoing_call_id": "c1"}):
        for k, v in state.items():
            setattr(a, k, v)
        check(f"in a call ({', '.join(state)}): not listened to", a.should_listen_sound() is False)
        for k in state:
            setattr(a, k, False if k == "call_window" else None)
    await a.on_sound_activity(True)
    await a.on_sound_activity(False)
    check("sound_activity sent to the server (true then false, nothing else)",
          sent == [{"type": "sound_activity", "active": True}, {"type": "sound_activity", "active": False}], sent)
    a.registered = False
    sent.clear()
    await a.on_sound_activity(True)
    check("not connected: nothing sent", sent == [])
    check("agent state for the self-repair still right", a.agent_state()["inCall"] is False)


asyncio.run(reading())
asyncio.run(agent_behaviour())

real_config = (Path(__file__).resolve().parents[1] / "config.py").read_text(encoding="utf-8")
check("config.py: VOICE_REACTION = True by default", "\nVOICE_REACTION = True\n" in real_config)
install = (Path(__file__).resolve().parents[1] / "install.sh").read_text(encoding="utf-8")
check("install.sh keeps VOICE_REACTION on update", '"VOICE_REACTION"' in install)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
