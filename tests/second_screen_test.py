# Second screen plugged or unplugged while the Raspberry runs
# (PLAN_SECOND_ECRAN.md, task 3): the agent checks every 30 s
# (check_second_screen) and restarts the kiosk (both windows opened again)
# only outside a ringing call or a call; during one, at its end. The first
# check only notes the screen; a kiosk that cannot be restarted never
# stops the agent.
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Raspberry_receiver/

cfg = types.ModuleType("config")
cfg.LANGUAGE = "fr"; cfg.RASPBERRY_ID = "rpi-screen"; cfg.DEVICE_SECRET = "secret"
cfg.SERVER_URL = "wss://x"; cfg.UNAUTHORIZED_RETRY_DELAY = 30; cfg.CALL_DURATION = 30
cfg.MOUSE_DEVICE = None; cfg.MOUSE_RETRY_DELAY = 5
sys.modules["config"] = cfg

tv = types.ModuleType("tv_control")
tv.tv_on_and_accept = lambda: None
tv.tv_return = lambda: None
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


screen = {"size": None}
agent.display_mode.second_screen = lambda: screen["size"]
a = agent.TVControlAgent()
restarts = []
a.restart_kiosk = lambda: restarts.append(True)

a.check_second_screen()
check("first check, no second screen: noted, kiosk not restarted", restarts == [])
screen["size"] = (1024, 600)
a.check_second_screen()
check("second screen plugged, no call: kiosk restarted once", restarts == [True])
a.check_second_screen()
check("still there: not restarted again", restarts == [True])

screen["size"] = None
a.call_window, a.current_call_id = True, "ring-1"
a.check_second_screen()
check("unplugged while it rings: not restarted", restarts == [True])
a.call_window, a.current_call_id = False, None
a.active_call_id = "call-1"
a.check_second_screen()
check("... nor during the call", restarts == [True])
a.active_call_id = None
a.check_second_screen()
check("call over: restarted at the next check", restarts == [True, True])
a.check_second_screen()
check("... once only", restarts == [True, True])

screen["size"] = (1024, 600)
a.outgoing_call_id = "out-1"
a.check_second_screen()
screen["size"] = None
a.check_second_screen()
a.outgoing_call_id = None
a.check_second_screen()
check("plugged then unplugged during a call made from this TV: nothing to do after it", restarts == [True, True])

b = agent.TVControlAgent()
b_restarts = []
b.restart_kiosk = lambda: b_restarts.append(True)
screen["size"] = (800, 480)
b.check_second_screen()
check("agent started with the screen already there: kiosk not restarted (it opened both windows)", b_restarts == [])

calls = []


def fake_run(command, **kwargs):
    calls.append(command)
    return types.SimpleNamespace(returncode=0)


agent.subprocess.run = fake_run
c = agent.TVControlAgent()
c.restart_kiosk()
check("restart_kiosk: Chromium of this user stopped (systemd starts the kiosk again)",
      len(calls) == 1 and calls[0][0] == "pkill" and "-x" in calls[0] and calls[0][-1] == "chromium" and "-u" in calls[0], calls)


def broken_run(command, **kwargs):
    raise OSError("no pkill")


agent.subprocess.run = broken_run
try:
    c.restart_kiosk()
    check("restart_kiosk that fails: message, no exception", True)
except Exception as e:
    check("restart_kiosk that fails: message, no exception", False, e)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
