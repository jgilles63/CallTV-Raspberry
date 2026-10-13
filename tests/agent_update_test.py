# Agent: installed version sent to the server, update request of the server
# (update_request): only a valid version name is written for update.sh.
import asyncio
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Raspberry_receiver/

tmp = Path(tempfile.mkdtemp())
cfg = types.ModuleType("config")
cfg.LANGUAGE = "fr"; cfg.RASPBERRY_ID = "rpi-update"; cfg.DEVICE_SECRET = "secret"
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


async def main():
    a = agent.TVControlAgent()
    sent = []

    async def capture(data):
        sent.append(data)

    a.send_message = capture
    request = tmp / "update_request"

    await a.register_device()
    check("no VERSION file: version \"unknown\" sent", sent[-1].get("version") == "unknown", sent[-1].get("version"))
    (tmp / "VERSION").write_text("v0.2.0\n", encoding="utf-8")
    await a.register_device()
    check("installed version sent at registration", sent[-1].get("version") == "v0.2.0")
    (tmp / "VERSION").write_text('v0.2.0-3-gabc"<x>\n', encoding="utf-8")
    await a.register_device()
    check("version cleaned (no quotes or symbols)", sent[-1].get("version") == "v0.2.0-3-gabcx", sent[-1].get("version"))
    (tmp / "VERSION").write_text("v0.2.0\n", encoding="utf-8")

    await a.handle_message({"type": "update_request", "requestId": "r1", "version": "v0.2.1"})
    check("valid version: written for update.sh", request.read_text(encoding="utf-8") == "v0.2.1\n")
    check("... and accepted (with the installed version)",
          sent[-1] == {"type": "update_ack", "requestId": "r1", "status": "accepted", "version": "v0.2.1", "installed": "v0.2.0"}, sent[-1])
    check("no temporary file left", not (tmp / "update_request.tmp").exists())

    for bad in ("v1; rm -rf ~", "0.2.1", "v0.2.1\nv9", "v0.2.1\n", "latest", "", None, 3, ["v0.2.1"], "v0.2.1 "):
        request.unlink(missing_ok=True)
        await a.handle_message({"type": "update_request", "requestId": "r2", "version": bad})
        check(f"invalid version {bad!r}: nothing written, refused",
              not request.exists() and sent[-1]["status"] == "invalid" and sent[-1]["version"] is None)

    cfg.BASE_DIR = tmp / "missing" / "folder"
    await a.handle_message({"type": "update_request", "requestId": "r3", "version": "v0.2.1"})
    check("request file not writable: error told, agent goes on", sent[-1]["status"] == "error")


asyncio.run(main())
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
