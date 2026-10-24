# TV in standby or on (HDMI-CEC power status), told to the TV page every 30 s
# (agent.report_tv_state, tv_state): the page rests while nobody watches
# (heat of the Raspberry). Checks: standby and going to standby = not
# watched; on, waking up or no CEC answer (computer monitor) = watched;
# nothing asked during a ringing call or a call, nor before registration; a
# CEC error never stops the agent.
import asyncio
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Raspberry_receiver/

cfg = types.ModuleType("config")
cfg.LANGUAGE = "fr"; cfg.RASPBERRY_ID = "rpi-tvstate"; cfg.DEVICE_SECRET = "secret"
cfg.SERVER_URL = "wss://x"; cfg.UNAUTHORIZED_RETRY_DELAY = 30; cfg.CALL_DURATION = 30
cfg.MOUSE_DEVICE = None; cfg.MOUSE_RETRY_DELAY = 5
sys.modules["config"] = cfg

power = {"value": "on", "asked": 0, "error": False}


def fake_tv_power(adapter=None):
    power["asked"] += 1
    if power["error"]:
        raise OSError("cec-ctl missing")
    return power["value"]


tv = types.ModuleType("tv_control")
tv.tv_on_and_accept = lambda: None
tv.tv_return = lambda: None
tv.tv_power = fake_tv_power
sys.modules["tv_control"] = tv
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

    await a.report_tv_state()
    check("not registered yet: nothing asked, nothing sent", sent == [] and power["asked"] == 0)
    a.registered = True
    for value, watching in (("standby", False), ("to-standby", False), ("on", True), ("to-on", True), (None, True)):
        sent.clear()
        power["value"] = value
        await a.report_tv_state()
        check(f"TV {value}: tv_state watching={watching}", sent == [{"type": "tv_state", "watching": watching}], sent)
    sent.clear()
    power["value"] = "standby"
    await a.report_tv_state()
    await a.report_tv_state()
    check("same state: told again at each check (a reloaded TV page gets it back)", len(sent) == 2)

    sent.clear()
    asked = power["asked"]
    a.call_window, a.current_call_id = True, "ring-1"
    await a.report_tv_state()
    a.call_window, a.current_call_id = False, None
    a.active_call_id = "call-1"
    await a.report_tv_state()
    a.active_call_id = None
    check("ringing or in a call: the TV is not asked (CEC kept for the call), nothing sent",
          sent == [] and power["asked"] == asked)

    power["error"] = True
    try:
        await a.report_tv_state()
        check("CEC error: nothing sent, no exception", sent == [])
    except Exception as e:
        check("CEC error: nothing sent, no exception", False, e)


asyncio.run(main())
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
