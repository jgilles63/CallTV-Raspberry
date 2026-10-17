# Remote control of the TV through HDMI-CEC (remote_keys.py and agent.py).
# Keys and keyboards simulated from a real Pi on a Hisense TV (17/10/2026):
# the kernel makes a keyboard "vc4-hdmi-0" (rc device with the "cec"
# protocol); arrows, OK = KEY_OK, Back = KEY_EXIT. Checks: keys translated
# (repeats for the arrows only), CEC keyboards found by their rc device and
# grabbed, repeats limited, keyboard lost then searched again; agent: OK answers and Back
# declines while it rings, Back hangs up a received call, otherwise the key
# goes to the TV page (remote_key), the Raspberry stays declared to the TV.
import asyncio
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Raspberry_receiver/

EV_KEY = 1
KEY_CODES = {103: "KEY_UP", 108: "KEY_DOWN", 105: "KEY_LEFT", 106: "KEY_RIGHT", 352: "KEY_OK",
             174: "KEY_EXIT", 158: "KEY_BACK", 28: "KEY_ENTER", 1: "KEY_ESC", 200: "KEY_PLAYCD",
             113: ["KEY_MIN_INTERESTING", "KEY_MUTE"], 353: "KEY_SELECT"}
CODE = {name: code for code, name in KEY_CODES.items() if isinstance(name, str)}


class Event:
    def __init__(self, code, value, type_=EV_KEY):
        self.type, self.code, self.value = type_, code, value


class FakeDevice:
    """Input device of the kernel; events: list of Event, then OSError (unplugged)."""
    devices = {}

    def __init__(self, path):
        spec = FakeDevice.devices[path]
        self.path, self.name, self.events = path, spec["name"], list(spec.get("events", []))
        self.grabbed = self.closed = False
        spec["opened"] = self
        spec.setdefault("all", []).append(self)

    def grab(self):
        self.grabbed = True

    def close(self):
        self.closed = True

    async def async_read_loop(self):
        for event in self.events:
            yield event
        raise OSError("No such device")


evdev = types.ModuleType("evdev")
evdev.InputDevice = FakeDevice
evdev.list_devices = lambda: list(FakeDevice.devices)
evdev.ecodes = types.SimpleNamespace(EV_KEY=EV_KEY, KEY=KEY_CODES, BTN_LEFT=272, REL_X=0, EV_REL=2)
sys.modules["evdev"] = evdev

cfg = types.ModuleType("config")
cfg.LANGUAGE = "fr"; cfg.RASPBERRY_ID = "rpi-remote"; cfg.DEVICE_SECRET = "secret"
cfg.SERVER_URL = "wss://x"; cfg.UNAUTHORIZED_RETRY_DELAY = 30; cfg.CALL_DURATION = 30
cfg.MOUSE_DEVICE = None; cfg.MOUSE_RETRY_DELAY = 5; cfg.BASE_DIR = Path(tempfile.mkdtemp())
sys.modules["config"] = cfg

tv_calls = []
tv = types.ModuleType("tv_control")
tv.tv_on_and_accept = lambda: tv_calls.append("on")
tv.tv_return = lambda: tv_calls.append("return")
tv.ensure_cec_ready = lambda: tv_calls.append("ready")
sys.modules["tv_control"] = tv


class FakeSound:
    def __init__(self):
        self.stopped = 0

    def play(self, name):
        pass

    def stop(self):
        self.stopped += 1


audio = types.ModuleType("tts_audio")
audio.AlertSound = FakeSound
sys.modules["tts_audio"] = audio

import remote_keys  # noqa: E402
import agent  # noqa: E402

passed = failed = 0


def check(label, condition, detail=""):
    global passed, failed
    passed, failed = passed + bool(condition), failed + (not condition)
    print(f"{'OK ' if condition else 'KO '} {label} {detail}")


# --- Keys translated ---
key = lambda name, value=1: remote_keys.key_of(Event(CODE[name], value))  # noqa: E731
check("arrows", [key(n) for n in ("KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT")] == ["up", "down", "left", "right"])
check("OK of the Hisense remote (KEY_OK) and other OK keys: ok",
      [key(n) for n in ("KEY_OK", "KEY_SELECT", "KEY_ENTER")] == ["ok"] * 3)
check("Back of the Hisense remote (KEY_EXIT) and other back keys: back",
      [key(n) for n in ("KEY_EXIT", "KEY_BACK", "KEY_ESC")] == ["back"] * 3)
check("key released: nothing", key("KEY_OK", 0) is None and key("KEY_UP", 0) is None)
check("arrow held down: repeated", key("KEY_DOWN", 2) == "down")
check("OK or Back held down: not repeated (no double answer)", key("KEY_OK", 2) is None and key("KEY_EXIT", 2) is None)
check("other keys (Play, Mute...): nothing", key("KEY_PLAYCD") is None and remote_keys.key_of(Event(113, 1)) is None)
check("other events (EV_SYN...): nothing", remote_keys.key_of(Event(0, 0, type_=0)) is None)

# --- CEC keyboards found through the rc devices of the kernel ---
rc_dir = tempfile.mkdtemp()
for rc, protocols, name in (("rc0", "[cec]\n", "vc4-hdmi-0"), ("rc1", "[cec]\n", "vc4-hdmi-1"),
                            ("rc2", "lirc nec rc-5\n", "gpio_ir_recv")):
    os.makedirs(os.path.join(rc_dir, rc, "input7"))
    Path(rc_dir, rc, "protocols").write_text(protocols)
    Path(rc_dir, rc, "input7", "name").write_text(name + "\n")
remote_keys.RC_DIR = rc_dir
check("names of the CEC keyboards (not the infrared receiver)", remote_keys.cec_keyboard_names() == {"vc4-hdmi-0", "vc4-hdmi-1"})
FakeDevice.devices = {
    "/dev/input/event0": {"name": "vc4-hdmi-0"},
    "/dev/input/event1": {"name": "vc4-hdmi-0 HDMI Jack"},
    "/dev/input/event4": {"name": "HS6209 2.4G Mouse"},
    "/dev/input/event6": {"name": "USB  AUDIO  "},
}
found = remote_keys.find_keyboards()
check("only the CEC keyboard found (not the HDMI jack, the mouse, the speaker)",
      [d.path for d in found] == ["/dev/input/event0"], [d.path for d in found])
check("the other devices closed", all(FakeDevice.devices[p]["opened"].closed for p in FakeDevice.devices if p != "/dev/input/event0"))


async def listening():
    received = []

    async def on_key(k):
        received.append(k)

    FakeDevice.devices = {"/dev/input/event0": {"name": "vc4-hdmi-0", "events": [
        Event(CODE["KEY_RIGHT"], 1), Event(CODE["KEY_RIGHT"], 0), Event(CODE["KEY_OK"], 1), Event(CODE["KEY_OK"], 0),
        Event(0, 0, type_=0), Event(CODE["KEY_EXIT"], 1), Event(CODE["KEY_EXIT"], 0)]}}
    task = asyncio.create_task(remote_keys.listen(on_key, retry_delay=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    check("keys read in order: right, ok, back (then the keyboard is lost)", received[:3] == ["right", "ok", "back"], received)
    first = FakeDevice.devices["/dev/input/event0"]["all"][0]
    check("keyboard grabbed (Chromium does not get the keys twice) and closed when lost", first.grabbed and first.closed)
    check("keyboard lost: searched again (read again)", received.count("right") >= 2, received)

    # An arrow held down: repeats limited (server limit: 100 messages in 10 s)
    received.clear()
    FakeDevice.devices = {"/dev/input/event0": {"name": "vc4-hdmi-0", "events":
                          [Event(CODE["KEY_DOWN"], 1)] + [Event(CODE["KEY_DOWN"], 2)] * 30 + [Event(CODE["KEY_DOWN"], 0)]}}
    task = asyncio.create_task(remote_keys.listen(on_key, retry_delay=10))
    await asyncio.sleep(0.05)
    task.cancel()
    check("arrow held down: first press sent, repeats limited (not 31 keys at once)",
          received[0] == "down" and 2 <= len(received) <= 3, f"{len(received)} keys")

    FakeDevice.devices = {}
    received.clear()
    task = asyncio.create_task(remote_keys.listen(on_key, retry_delay=0.01))
    await asyncio.sleep(0.03)
    task.cancel()
    check("no CEC keyboard (monitor, TV without CEC): no crash, no key", received == [])


async def agent_behaviour():
    a = agent.TVControlAgent()
    sent = []

    async def capture(data):
        sent.append(data)

    a.send_message = capture

    # Outside calls: the keys go to the TV page (its menu)
    for k in ("right", "ok", "back"):
        await a.on_remote_key(k)
    check("outside calls: keys sent to the TV page (remote_key)",
          sent == [{"type": "remote_key", "key": "right"}, {"type": "remote_key", "key": "ok"},
                   {"type": "remote_key", "key": "back"}], sent)

    # While it rings: OK answers like the mouse
    sent.clear()
    a.call_window, a.current_call_id = True, "call-1"
    await a.on_remote_key("left")
    check("while it rings: arrows ignored", sent == [])
    await a.on_remote_key("ok")
    check("while it rings: OK answers (accept_call, TV turned on)",
          {"type": "accept_call", "callId": "call-1"} in sent and a.active_call_id == "call-1" and "on" in tv_calls, sent)

    # During the received call: Back hangs up
    sent.clear()
    await a.on_remote_key("right")
    check("during the call: arrows go to the page", sent == [{"type": "remote_key", "key": "right"}])
    sent.clear()
    await a.on_remote_key("back")
    check("during the call: Back hangs up", sent == [{"type": "hangup", "callId": "call-1"}] and a.active_call_id is None, sent)

    # While it rings: Back declines
    sent.clear()
    tv_calls.clear()
    a.call_window, a.current_call_id = True, "call-2"
    stops = a.alert_sound.stopped
    await a.on_remote_key("back")
    check("while it rings: Back declines (hangup, ringtone stopped, TV given back)",
          sent == [{"type": "hangup", "callId": "call-2"}] and not a.call_window and a.current_call_id is None
          and a.alert_sound.stopped > stops and tv_calls == ["return"], sent)

    # The Raspberry stays declared to the TV
    tv_calls.clear()
    a.keep_cec_ready()
    check("keep_cec_ready: tv_control.ensure_cec_ready called", tv_calls == ["ready"])
    tv.ensure_cec_ready = lambda: (_ for _ in ()).throw(OSError("cec-ctl missing"))
    a.keep_cec_ready()
    check("keep_cec_ready: an error does not stop the agent", True)


asyncio.run(listening())
asyncio.run(agent_behaviour())

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
