# Resolution of the screen (display_mode.py): a 4K TV is set to 1920 x 1080
# at the highest refresh rate up to 60 Hz; a screen of 1920 pixels or less is
# never changed. Outputs of wlr-randr shortened from real Pis (17/10/2026):
# Hisense TV in 3840 x 2160 at 30 Hz, computer monitor in 1920 x 1080 at 75 Hz.
# Also: config.SCREEN_MODE = None, no 1080p mode, wlr-randr missing, the
# Wayland socket found without XDG_RUNTIME_DIR, the health report line.
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Raspberry_receiver/

cfg = types.ModuleType("config")
cfg.BASE_DIR = Path(tempfile.gettempdir())
cfg.LANGUAGE = "fr"
sys.modules["config"] = cfg

import display_mode as d  # noqa: E402

passed = failed = 0


def check(label, condition, detail=""):
    global passed, failed
    passed, failed = passed + bool(condition), failed + (not condition)
    print(f"{'OK ' if condition else 'KO '} {label} {detail}")


TV_4K = '''HDMI-A-1 "Hisense Electric Co., Ltd. HISENSE 0x00000001 (HDMI-A-1)"
  Make: Hisense Electric Co., Ltd.
  Enabled: yes
  Modes:
    3840x2160 px, 30.000000 Hz (preferred, current)
    4096x2160 px, 30.000000 Hz
    3840x2160 px, 25.000000 Hz
    1920x1080 px, 60.000000 Hz
    1920x1080 px, 59.939999 Hz
    1920x1080 px, 50.000000 Hz
    1920x1080 px, 30.000000 Hz
    1280x720 px, 60.000000 Hz
  Position: 0,0
  Transform: normal
  Scale: 1.000000
'''
MONITOR = '''HDMI-A-1 "Acer Technologies KA242Y (HDMI-A-1)"
  Enabled: yes
  Modes:
    1920x1080 px, 74.973000 Hz (current)
    1920x1080 px, 60.000000 Hz (preferred)
    1280x720 px, 60.000000 Hz
'''
TV_4K_NO_1080 = '''HDMI-A-1 "Odd TV"
  Enabled: yes
  Modes:
    3840x2160 px, 60.000000 Hz (preferred, current)
    2560x1440 px, 60.000000 Hz
'''
TWO_OUTPUTS = TV_4K + '''HDMI-A-2 "Second screen"
  Enabled: no
  Modes:
    3840x2160 px, 30.000000 Hz (current)
    1920x1080 px, 60.000000 Hz
'''


class FakeRandr:
    def __init__(self, listing):
        self.listing = listing
        self.commands = []

    def run(self, command):
        self.commands.append(command)
        if command == ["wlr-randr"]:
            return self.listing
        return ""

    def set_commands(self):
        return [c for c in self.commands if "--mode" in c]


def with_listing(listing):
    fake = FakeRandr(listing)
    d.run = fake.run
    return fake


# --- Parsing ---
outputs = d.parse_outputs(TV_4K)
check("TV: one output, enabled, current mode 3840x2160 30 Hz",
      len(outputs) == 1 and outputs[0]["name"] == "HDMI-A-1" and outputs[0]["enabled"]
      and outputs[0]["current"] == (3840, 2160, 30.0), outputs)
check("TV: all its modes read", len(outputs[0]["modes"]) == 8)
check("best mode: 1920x1080 at 60 Hz (not 59.94, not 30)", d.best_mode(outputs[0]["modes"]) == (1920, 1080, 60.0))
check("monitor at 75 Hz: 1080p mode up to 60 Hz chosen if needed",
      d.best_mode(d.parse_outputs(MONITOR)[0]["modes"]) == (1920, 1080, 60.0))
check("no 1080p mode: none", d.best_mode(d.parse_outputs(TV_4K_NO_1080)[0]["modes"]) is None)
check("disabled output read as disabled", d.parse_outputs(TWO_OUTPUTS)[1]["enabled"] is False)
check("empty or missing output: nothing", d.parse_outputs("") == [] and d.parse_outputs(None) == [])

# --- Setting the mode ---
fake = with_listing(TV_4K)
changed = d.ensure_screen_mode()
check("4K TV: set to 1920x1080 at 60 Hz", fake.set_commands() == [["wlr-randr", "--output", "HDMI-A-1", "--mode", "1920x1080@60.000000Hz"]],
      fake.set_commands())
check("change returned", changed == [("HDMI-A-1", (1920, 1080, 60.0))])
fake = with_listing(MONITOR)
check("monitor already 1920 wide (75 Hz): never changed", d.ensure_screen_mode() == [] and fake.set_commands() == [])
fake = with_listing(TV_4K_NO_1080)
check("4K TV without 1080p mode: left as it is", d.ensure_screen_mode() == [] and fake.set_commands() == [])
fake = with_listing(TWO_OUTPUTS)
d.ensure_screen_mode()
check("disabled output: not changed", [c[2] for c in fake.set_commands()] == ["HDMI-A-1"], fake.set_commands())
cfg.SCREEN_MODE = None
fake = with_listing(TV_4K)
check("SCREEN_MODE = None: 4K kept, wlr-randr not even run", d.ensure_screen_mode() == [] and fake.commands == [])
cfg.SCREEN_MODE = "1080p"
fake = with_listing(None)
check("wlr-randr missing or no Wayland: nothing, no crash", d.ensure_screen_mode() == [])

# --- Current mode (health report) ---
with_listing(TV_4K)
check("current mode: [(HDMI-A-1, (3840, 2160, 30.0))]", d.current_mode() == [("HDMI-A-1", (3840, 2160, 30.0))])
with_listing(TWO_OUTPUTS)
check("current mode: enabled outputs only", [name for name, _ in d.current_mode()] == ["HDMI-A-1"])

# --- Environment (system services: no XDG_RUNTIME_DIR, no WAYLAND_DISPLAY) ---
runtime = tempfile.mkdtemp()
for name in ("wayland-1", "wayland-1.lock"):
    Path(runtime, name).write_text("")
saved = {k: os.environ.pop(k, None) for k in ("XDG_RUNTIME_DIR", "WAYLAND_DISPLAY")}
env = d.wayland_env()
check("XDG_RUNTIME_DIR added (/run/user/<uid>)", env["XDG_RUNTIME_DIR"].startswith("/run/user/"), env["XDG_RUNTIME_DIR"])
os.environ["XDG_RUNTIME_DIR"] = runtime
check("Wayland socket found in it (not the .lock)", d.wayland_env()["WAYLAND_DISPLAY"] == "wayland-1")
os.environ["WAYLAND_DISPLAY"] = "wayland-7"
check("WAYLAND_DISPLAY already set: kept", d.wayland_env()["WAYLAND_DISPLAY"] == "wayland-7")
for k, v in saved.items():
    if v is None:
        os.environ.pop(k, None)
    else:
        os.environ[k] = v

# --- Health report line ---
import diagnostics  # noqa: E402
with_listing(TV_4K)
check("report: 4K TV still in 4K -> warn", diagnostics.check_screen() == {"id": "screen", "status": "warn", "value": "HDMI-A-1: 3840x2160 30 Hz"},
      diagnostics.check_screen())
with_listing(MONITOR)
check("report: 1920x1080 -> ok", diagnostics.check_screen() == {"id": "screen", "status": "ok", "value": "HDMI-A-1: 1920x1080 74.973 Hz"},
      diagnostics.check_screen())
with_listing(None)
check("report: unknown -> info", diagnostics.check_screen()["status"] == "info")

real_config = (Path(__file__).resolve().parents[1] / "config.py").read_text(encoding="utf-8")
check("config.py: SCREEN_MODE = \"1080p\" by default", '\nSCREEN_MODE = "1080p"\n' in real_config)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
