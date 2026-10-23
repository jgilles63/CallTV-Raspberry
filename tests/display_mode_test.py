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

# --- Second screen on HDMI-A-2 (PLAN_SECOND_ECRAN.md; seen on 23/10/2026: TV + Acer) ---
SMALL_SCREEN = '''HDMI-A-2 "Touch screen 7in"
  Enabled: yes
  Modes:
    1024x600 px, 60.000000 Hz (preferred, current)
'''
BIG_SCREEN = '''HDMI-A-2 "Big monitor"
  Enabled: yes
  Modes:
    2560x1440 px, 59.951000 Hz (preferred, current)
    1920x1080 px, 60.000000 Hz
'''
check("outputs: TV on HDMI-A-1, second screen on HDMI-A-2", d.TV_OUTPUT == "HDMI-A-1" and d.SECOND_OUTPUT == "HDMI-A-2")
cfg.SECOND_SCREEN = "auto"
with_listing(MONITOR)
check("TV alone: no second screen", d.second_screen() is None)
with_listing(MONITOR + SMALL_SCREEN)
check("TV + 7in screen on HDMI-A-2: its size (1024, 600)", d.second_screen() == (1024, 600), d.second_screen())
with_listing(SMALL_SCREEN.replace("HDMI-A-2", "HDMI-A-1"))
check("a small screen on HDMI-A-1 is the TV, not a second screen", d.second_screen() is None)
with_listing(TWO_OUTPUTS)
check("HDMI-A-2 disabled: no second screen", d.second_screen() is None)
with_listing(SMALL_SCREEN)
check("a TV alone on HDMI-A-2 (the other port): one screen, not a second screen (review of 23/10/2026)", d.second_screen() is None)
with_listing(TWO_OUTPUTS.replace("HDMI-A-1", "HDMI-A-X").replace("HDMI-A-2", "HDMI-A-1").replace("HDMI-A-X", "HDMI-A-2"))
check("HDMI-A-1 disabled, screen on HDMI-A-2: not a second screen", d.second_screen() is None)
cfg.SECOND_SCREEN = False
with_listing(MONITOR + SMALL_SCREEN)
check("SECOND_SCREEN = False: never a second screen", d.second_screen() is None)
cfg.SECOND_SCREEN = "auto"
with_listing(None)
check("wlr-randr missing: no second screen, no crash", d.second_screen() is None)
del cfg.SECOND_SCREEN
with_listing(MONITOR + SMALL_SCREEN)
check("older config.py without SECOND_SCREEN: \"auto\"", d.second_screen() == (1024, 600))
import contextlib  # noqa: E402
import io  # noqa: E402
with_listing(MONITOR + SMALL_SCREEN)
out = io.StringIO()
with contextlib.redirect_stdout(out):
    code = d.main(["--second"])
check("display_mode.py --second (launch_chromium.sh): prints 1024x600, exit 0", code == 0 and out.getvalue().strip() == "1024x600", out.getvalue())
with_listing(MONITOR)
out = io.StringIO()
with contextlib.redirect_stdout(out):
    code = d.main(["--second"])
check("display_mode.py --second without second screen: nothing printed, exit 1", code == 1 and out.getvalue() == "")
fake = with_listing(MONITOR + BIG_SCREEN)
d.ensure_screen_mode()
check("second screen wider than 1920: set to 1920x1080 like the TV",
      fake.set_commands() == [["wlr-randr", "--output", "HDMI-A-2", "--mode", "1920x1080@60.000000Hz"]], fake.set_commands())

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
cfg.SECOND_SCREEN = "auto"
with_listing(MONITOR + SMALL_SCREEN)
check("report: second screen -> ok, its output and size",
      diagnostics.check_second_screen() == {"id": "second_screen", "status": "ok", "value": "HDMI-A-2: 1024x600"},
      diagnostics.check_second_screen())
with_listing(MONITOR)
check("report: no second screen -> info", diagnostics.check_second_screen() == {"id": "second_screen", "status": "info", "value": "-"})
# (the label of the server, private repository, is checked by its own tests)
check("report: second screen line translated (fr, en, es)",
      all(__import__("i18n").MESSAGES[lang].get("diag.check.second_screen") for lang in ("fr", "en", "es")))

real_config = (Path(__file__).resolve().parents[1] / "config.py").read_text(encoding="utf-8")
check("config.py: SCREEN_MODE = \"1080p\" by default", '\nSCREEN_MODE = "1080p"\n' in real_config)
check("config.py: SECOND_SCREEN = \"auto\" by default", '\nSECOND_SCREEN = "auto"\n' in real_config)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
