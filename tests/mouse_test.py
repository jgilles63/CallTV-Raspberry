# Tests the mouse detection of the real agent.py with a simulated evdev module:
# devices are plugged, unplugged and replugged while mouse_listener() runs.
import asyncio
import errno
import sys
import tempfile
import types
from pathlib import Path

P = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Raspberry_receiver/

# --- Stub configuration (avoids creating folders in the home directory) ---
cfg = types.ModuleType("config")
cfg.LANGUAGE = "fr"
cfg.CACHE_DIR = Path(P) / "cache"
cfg.MOUSE_DEVICE = None
cfg.MOUSE_RETRY_DELAY = 0.05
cfg.RINGTONE_PATH = "x.wav"; cfg.CALL_DURATION = 30; cfg.MAX_CACHED_CALLS = 30
cfg.MAX_CALLER_NAME_LENGTH = 30; cfg.VOICE_VOLUME = 1.5; cfg.RINGTONE_VOLUME = 0.2
cfg.SERVER_URL = "wss://unused"; cfg.UNAUTHORIZED_RETRY_DELAY = 30
cfg.RASPBERRY_ID = "rpi-test"; cfg.DEVICE_SECRET = "s"
sys.modules["config"] = cfg

# --- Simulated evdev ---
EV_KEY, EV_REL, EV_ABS = 1, 2, 3
BTN_LEFT, REL_X, KEY_A = 272, 0, 30
plugged = {}        # path -> device description (what is physically connected)
opened = []         # every FakeDevice opened, to check they get closed


class FakeDevice:
    def __init__(self, path):
        if path not in plugged:
            raise OSError(errno.ENOENT, "No such device")
        self.path = path
        self.name = plugged[path]["name"]
        self._caps = plugged[path]["caps"]
        self.queue = plugged[path]["queue"]
        self.closed = False
        opened.append(self)

    def capabilities(self):
        return self._caps

    def close(self):
        self.closed = True

    async def async_read_loop(self):
        while True:
            item = await self.queue.get()
            if item == "UNPLUG":
                raise OSError(errno.ENODEV, "No such device")
            yield types.SimpleNamespace(type=EV_KEY, code=item, value=1)


def plug(path, name, caps):
    plugged[path] = {"name": name, "caps": caps, "queue": asyncio.Queue()}


def unplug(path):
    plugged.pop(path)["queue"].put_nowait("UNPLUG")


def click(path, code=BTN_LEFT):
    plugged[path]["queue"].put_nowait(code)


evdev = types.ModuleType("evdev")
evdev.InputDevice = FakeDevice
evdev.list_devices = lambda: list(plugged)
evdev.ecodes = types.SimpleNamespace(EV_KEY=EV_KEY, EV_REL=EV_REL, BTN_LEFT=BTN_LEFT, REL_X=REL_X)
sys.modules["evdev"] = evdev

import agent  # noqa: E402  (the real agent, with the simulated evdev)

MOUSE = {EV_KEY: [BTN_LEFT, 273], EV_REL: [REL_X, 1]}
KEYBOARD = {EV_KEY: [KEY_A, 31]}
TOUCHPAD = {EV_KEY: [BTN_LEFT, 330], EV_ABS: [0, 1]}

results = []


def check(name, condition):
    results.append(condition)
    print(("✅ " if condition else "❌ ") + name)


async def main():
    a = agent.TVControlAgent()
    accepted = []

    async def fake_accept():
        accepted.append(a.call_window)
        a.call_window = False

    a.on_mouse_click_async = fake_accept
    pause = lambda: asyncio.sleep(0.2)

    task = asyncio.create_task(a.mouse_listener())

    # 1. Nothing plugged in
    await pause()
    check("no mouse: the agent keeps looking", not task.done())

    # 2. A keyboard and a touchpad, then a real mouse on another port
    plug("/dev/input/event3", "USB keyboard", KEYBOARD)
    plug("/dev/input/event5", "Touchpad", TOUCHPAD)
    plug("/dev/input/event7", "3D printed mouse", MOUSE)
    await pause()
    current = [d for d in opened if not d.closed]
    check("the real mouse is chosen (not the keyboard nor the touchpad)",
          len(current) == 1 and current[0].path == "/dev/input/event7")

    # 3. Click outside a call: ignored
    click("/dev/input/event7")
    await pause()
    check("click outside a call: ignored", accepted == [])

    # 4. Click during a call: answers
    a.call_window = True
    click("/dev/input/event7")
    await pause()
    check("click during a call: answers", accepted == [True])

    # 5. Other buttons are ignored
    a.call_window = True
    click("/dev/input/event7", code=273)  # right button
    await pause()
    check("right click: ignored", accepted == [True])
    a.call_window = False

    # 6. Unplug the mouse
    unplug("/dev/input/event7")
    unplug("/dev/input/event5")
    await pause()
    check("mouse unplugged: the agent keeps running", not task.done())
    check("every device opened is closed again",
          all(d.closed for d in opened if d.path != "/dev/input/event3") and
          all(d.closed for d in opened if d.path == "/dev/input/event3"))

    # 7. Replug on another USB port (another event number), another model
    plug("/dev/input/event9", "Other mouse", MOUSE)
    await pause()
    a.call_window = True
    click("/dev/input/event9")
    await pause()
    check("plugged into another port: found again and answers", accepted == [True, True])

    task.cancel()

    # 8. Forced device (MOUSE_DEVICE set): waits for it, ignores the others
    cfg.MOUSE_DEVICE = "/dev/input/by-id/usb-My_Mouse-event-mouse"
    accepted.clear()
    task = asyncio.create_task(a.mouse_listener())
    await pause()
    check("forced device absent: the agent waits (does not use another mouse)",
          not task.done() and all(d.closed or d.path != "/dev/input/event9" for d in opened[-1:]))
    plug(cfg.MOUSE_DEVICE, "My mouse", MOUSE)
    await pause()
    a.call_window = True
    click(cfg.MOUSE_DEVICE)
    await pause()
    check("forced device plugged in: used", accepted == [True])
    task.cancel()


asyncio.run(main())
print(f"\n{sum(results)} passed, {len(results) - sum(results)} failed")
sys.exit(0 if all(results) else 1)
