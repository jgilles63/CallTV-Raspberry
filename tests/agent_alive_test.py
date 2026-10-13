# Agent: alive signal to systemd (WatchdogSec) and state written for the
# self-repair (agent_state.json), TV page state told by the server (pong).
import asyncio
import json
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Raspberry_receiver/

tmp = Path(tempfile.mkdtemp())
cfg = types.ModuleType("config")
cfg.LANGUAGE = "fr"; cfg.RASPBERRY_ID = "rpi-alive"; cfg.DEVICE_SECRET = "secret"
cfg.SERVER_URL = "wss://x"; cfg.UNAUTHORIZED_RETRY_DELAY = 30; cfg.CALL_DURATION = 30
cfg.MOUSE_DEVICE = None; cfg.MOUSE_RETRY_DELAY = 5; cfg.BASE_DIR = tmp
sys.modules["config"] = cfg
tv = types.ModuleType("tv_control")
tv.tv_on_and_accept = tv.tv_return = lambda: None
sys.modules["tv_control"] = tv
audio = types.ModuleType("tts_audio")
audio.AlertSound = lambda: types.SimpleNamespace(play=lambda n: None, stop=lambda: None)
sys.modules["tts_audio"] = audio
evdev = types.ModuleType("evdev")
evdev.InputDevice = evdev.ecodes = evdev.list_devices = None
sys.modules["evdev"] = evdev

import agent  # noqa: E402

passed = failed = 0


def check(label, condition, detail=""):
    global passed, failed
    passed, failed = passed + bool(condition), failed + (not condition)
    print(f"{'OK ' if condition else 'KO '} {label} {detail}")


def state():
    return json.loads((tmp / "agent_state.json").read_text(encoding="utf-8"))


async def main():
    a = agent.TVControlAgent()
    notes = []
    a.notify_systemd = notes.append
    a.alive_interval = 0.05

    check("unknown page state at start", a.display_connected is None)
    task = asyncio.create_task(a.alive_task())
    await asyncio.sleep(0.12)
    check("alive signal sent to systemd repeatedly", notes.count("WATCHDOG=1") >= 2)
    s = state()
    check("state written: not connected, no call, page unknown",
          s["registered"] is False and s["inCall"] is False and s["displayConnected"] is None and s["rejected"] is False)
    check("no temporary file left", not (tmp / "agent_state.json.tmp").exists())

    await a.handle_message({"type": "register_ack"})
    await a.handle_message({"type": "pong", "displayConnected": False})
    await asyncio.sleep(0.08)
    s = state()
    check("connected, page told as NOT connected by the server", s["registered"] is True and s["displayConnected"] is False)
    await a.handle_message({"type": "pong", "displayConnected": True})
    await a.handle_message({"type": "pong"})
    await asyncio.sleep(0.08)
    check("pong without the field (older server): last value kept", state()["displayConnected"] is True)

    a.current_call_id = "call-1"
    await asyncio.sleep(0.08)
    check("received call: inCall", state()["inCall"] is True)
    a.current_call_id = None
    a.outgoing_call_id = "call-2"
    await asyncio.sleep(0.08)
    check("call from this TV: inCall", state()["inCall"] is True)
    a.outgoing_call_id = None
    a.call_window = True
    await asyncio.sleep(0.08)
    check("ringing: inCall", state()["inCall"] is True)
    a.call_window = False

    a.rejected_by_server = True
    await asyncio.sleep(0.08)
    check("refused by the server: told", state()["rejected"] is True)
    task.cancel()

    # end of a session: not connected, page unknown again
    class FakeWs:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        async def close(self):
            pass

        async def send(self, data):
            pass

    a.ws = FakeWs()
    a.registered = True
    a.display_connected = True
    await a.run_session()
    check("connection lost: not registered, page state unknown", a.registered is False and a.display_connected is None)

    # state file not writable: no crash
    cfg.BASE_DIR = tmp / "missing" / "folder"
    a.write_agent_state()
    check("state file not writable: agent goes on", True)

    # outside systemd: nothing sent, no error
    agent.os.environ.pop("NOTIFY_SOCKET", None)
    agent.TVControlAgent.notify_systemd("WATCHDOG=1")
    check("outside systemd (no NOTIFY_SOCKET): nothing done", True)


asyncio.run(main())
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
