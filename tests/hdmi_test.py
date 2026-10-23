# TV control with cec-ctl (tv_control.py), with simulated cec-ctl commands
# (subprocess.run), CEC adapters (/dev/cec*) and no waiting. Outputs taken
# from real Pis (17/10/2026): TV on HDMI 3 (3.0.0.0), computer monitor
# without CEC (1.0.0.0, no answer). Checks: the Raspberry is declared to the
# TV once (the TV then sends the keys of its remote control), the TV is turned
# on and switched to the input given by the TV (config.HDMI_PORT only when
# the TV gives none), the CEC answer given to the choice of the call sound,
# tv_return, no shell (no injection), cec-client never used again.
import importlib
import subprocess
import sys
import types
from pathlib import Path

REPO = str(Path(__file__).resolve().parents[1])  # Raspberry_receiver/
sys.path.insert(0, REPO)

passed = failed = 0


def check(label, condition, detail=""):
    global passed, failed
    passed, failed = passed + bool(condition), failed + (not condition)
    print(f"{'OK ' if condition else 'KO '} {label} {detail}")


def adapter_output(physical, declared):
    """Output of `cec-ctl -d /dev/cec0` (shortened from a real Pi)."""
    return (
        "Driver Info:\n\tDriver Name                : vc4_hdmi\n"
        "\tAdapter Name               : vc4-hdmi-0\n"
        f"\tPhysical Address           : {physical}\n"
        f"\tLogical Address Mask       : {'0x0100' if declared else '0x0000'}\n"
        "\tCEC Version                : 2.0\n"
    )


POWER_ON = "GIVE_DEVICE_POWER_STATUS (0x8f)\n    REPORT_POWER_STATUS (0x90):\n\tpwr-state: on (0x00)\n"
POWER_STANDBY = "    REPORT_POWER_STATUS (0x90):\n\tpwr-state: standby (0x01)\n"
POWER_TO_ON = "    REPORT_POWER_STATUS (0x90):\n\tpwr-state: in transition standby to on (0x02)\n"


class FakeCec:
    """Simulated CEC adapters: {path: {"physical", "declared", "power"}}."""

    def __init__(self, adapters):
        self.adapters = adapters
        self.commands = []

    def run(self, command, **kwargs):
        if isinstance(command, str) or kwargs.get("shell"):
            raise AssertionError(f"shell command: {command}")
        self.commands.append(command)
        assert command[0] == "cec-ctl" and command[1] == "-d", command
        adapter = self.adapters[command[2]]
        args = command[3:]
        out = ""
        if not args:
            out = adapter_output(adapter["physical"], adapter["declared"])
        elif args[0] == "--playback":
            adapter["declared"] = True
        elif "--give-device-power-status" in args:
            out = adapter.get("power") or ""
        return subprocess.CompletedProcess(command, 0, stdout=out, stderr="")

    def sent(self, *args):
        return [c for c in self.commands if tuple(c[3:3 + len(args)]) == args]


routes = []
audio = types.ModuleType("call_audio")
audio.route_call_audio = routes.append
sys.modules["call_audio"] = audio


def load(adapters, port=3):
    """tv_control with simulated adapters and config.HDMI_PORT = port (None: missing)."""
    cfg = types.ModuleType("config")
    if port is not None:
        cfg.HDMI_PORT = port
    sys.modules["config"] = cfg
    sys.modules.pop("tv_control", None)
    tv = importlib.import_module("tv_control")
    fake = FakeCec(adapters)
    tv.subprocess = types.SimpleNamespace(run=fake.run, SubprocessError=subprocess.SubprocessError,
                                          CompletedProcess=subprocess.CompletedProcess)
    tv.glob = types.SimpleNamespace(glob=lambda pattern: sorted(adapters))
    tv.time = types.SimpleNamespace(sleep=lambda s: None, monotonic=lambda: 0.0)
    threads = []

    class Thread:
        def __init__(self, target, daemon, args=()):
            self.target, self.args = target, args
            threads.append(self)

        def start(self):
            self.target(*self.args)

    tv.threading = types.SimpleNamespace(Thread=Thread)
    return tv, fake


source = Path(REPO, "tv_control.py").read_text(encoding="utf-8")
code_lines = [line for line in source.splitlines() if not line.lstrip().startswith("#")]
check("cec-client no longer run (it clears the CEC configuration when it ends)",
      not any('"cec-client' in line or "'cec-client" in line for line in code_lines))

# --- TV on HDMI 3, Raspberry not declared yet (after a reboot) ---
tv, fake = load({"/dev/cec0": {"physical": "3.0.0.0", "declared": False, "power": POWER_ON},
                 "/dev/cec1": {"physical": "f.f.f.f", "declared": False}})
check("adapter of the connected HDMI output found", tv.find_adapter()[0] == "/dev/cec0")
check("ensure_cec_ready: declared as playback, address given by the TV",
      tv.ensure_cec_ready() == ("/dev/cec0", "3.0.0.0")
      and fake.sent("--playback", "--osd-name", "AppelerMamie") != [])
before = len(fake.sent("--playback"))
tv.ensure_cec_ready()
check("already declared: not declared again", len(fake.sent("--playback")) == before)
check("TV on: power \"on\", it is a TV", tv.tv_power() == "on" and tv.tv_answers_cec())

routes.clear()
fake.commands.clear()
tv.tv_on_and_accept()
order = [c[3:] for c in fake.commands if c[3:]]
check("accept: TV turned on first (image-view-on to the TV)", order[0] == ["--to", "0", "--image-view-on"], order[:1])
check("then its power status asked (is it a TV?)", order[1] == ["--to", "0", "--give-device-power-status"], order[:2])
switches = fake.sent("--to", "15", "--active-source", "phys-addr=3.0.0.0")
check("TV switched to the input of the Raspberry 5 times (broadcast, 3.0.0.0)", len(switches) == 5, len(switches))
check("no inactive-source right after the switch (the TV keeps sending the keys)",
      fake.sent("--to", "0", "--inactive-source", "phys-addr=3.0.0.0") == [])
check("TV answering CEC: call sound routed with tv_present=True", routes == [True], routes)
tv.tv_return()
check("tv_return: inactive source to the TV", len(fake.sent("--to", "0", "--inactive-source", "phys-addr=3.0.0.0")) == 1)

for power, state in ((POWER_STANDBY, "standby"), (POWER_TO_ON, "to-on")):
    tv, fake = load({"/dev/cec0": {"physical": "3.0.0.0", "declared": True, "power": power}})
    routes.clear()
    tv.tv_on_and_accept()
    check(f"TV {state}: power \"{state}\", tv_present=True", tv.tv_power() == state and routes == [True], routes)

# --- Computer monitor without CEC (Pi of the tests) ---
tv, fake = load({"/dev/cec0": {"physical": "1.0.0.0", "declared": False, "power": None},
                 "/dev/cec1": {"physical": "f.f.f.f", "declared": False}})
routes.clear()
tv.tv_on_and_accept()
check("monitor without CEC: no answer, tv_present=False", tv.tv_power() is None and routes == [False], routes)

# --- The TV gives no physical address: config.HDMI_PORT ---
tv, fake = load({"/dev/cec0": {"physical": "f.f.f.f", "declared": False, "power": POWER_ON}}, port=2)
tv.tv_on_and_accept()
check("address from config.HDMI_PORT when the TV gives none (2.0.0.0)",
      len(fake.sent("--to", "15", "--active-source", "phys-addr=2.0.0.0")) == 5)
tv, fake = load({"/dev/cec0": {"physical": "f.f.f.f", "declared": False, "power": POWER_ON}}, port="4")
tv.tv_on_and_accept()
check("HDMI_PORT given as text \"4\": 4.0.0.0", len(fake.sent("--to", "15", "--active-source", "phys-addr=4.0.0.0")) == 5)
tv, fake = load({"/dev/cec0": {"physical": "f.f.f.f", "declared": False, "power": POWER_ON}}, port=None)
tv.tv_on_and_accept()
check("config.py older than HDMI_PORT: 3.0.0.0", len(fake.sent("--to", "15", "--active-source", "phys-addr=3.0.0.0")) == 5)
tv, fake = load({"/dev/cec0": {"physical": "f.f.f.f", "declared": False, "power": POWER_ON}}, port="3; rm -rf ~")
tv.tv_on_and_accept()
check("invalid HDMI_PORT: never inserted into a command, input 3 used",
      not any("rm -rf" in " ".join(c) for c in fake.commands)
      and len(fake.sent("--to", "15", "--active-source", "phys-addr=3.0.0.0")) == 5)

# --- No CEC adapter at all ---
tv, fake = load({})
routes.clear()
tv.tv_on_and_accept()
tv.tv_return()
check("no CEC adapter: nothing sent, call sound on the USB speaker",
      fake.commands == [] and routes == [False] and tv.ensure_cec_ready()[0] is None)

# --- cec-ctl missing ---
tv, fake = load({"/dev/cec0": {"physical": "3.0.0.0", "declared": True}})


def missing(command, **kwargs):
    raise FileNotFoundError("cec-ctl")


tv.subprocess.run = missing
routes.clear()
tv.tv_on_and_accept()
check("cec-ctl missing (v4l-utils not installed): no crash", routes == [False])

real_config = Path(REPO, "config.py").read_text(encoding="utf-8")
check("config.py: HDMI_PORT = 3 by default (used only without address from the TV)", "\nHDMI_PORT = 3\n" in real_config)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
