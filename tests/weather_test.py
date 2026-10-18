# Place of the weather of the home screen (ROADMAP 2.14): config.py gives the
# town, postal code and country (asked by install.sh, see install_test.sh);
# the agent sends them in register_device (weatherPlace), the server finds
# the weather. Checks: place sent (cleaned, None without town nor postal
# code), register_device message, line of the health report.
import asyncio
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Raspberry_receiver/

cfg = types.ModuleType("config")
cfg.LANGUAGE = "fr"; cfg.RASPBERRY_ID = "rpi-weather"; cfg.DEVICE_SECRET = "secret"
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

import agent  # noqa: E402
import diagnostics  # noqa: E402

passed = failed = 0


def check(label, condition, detail=""):
    global passed, failed
    passed, failed = passed + bool(condition), failed + (not condition)
    print(f"{'OK ' if condition else 'KO '} {label} {detail}")


def set_place(city, postcode, country):
    cfg.WEATHER_CITY, cfg.WEATHER_POSTCODE, cfg.WEATHER_COUNTRY = city, postcode, country


# --- Place sent by the agent ---
set_place("Clermont-Ferrand", "63000", "France")
check("town, postal code and country sent", agent.weather_place() == {"city": "Clermont-Ferrand", "postcode": "63000", "country": "France"},
      agent.weather_place())
set_place(None, None, None)
check("nothing set: no place (no weather)", agent.weather_place() is None)
set_place("", "  ", "France")
check("country alone: no place (town or postal code needed)", agent.weather_place() is None)
set_place(None, "63000", None)
check("postal code alone: enough", agent.weather_place() == {"city": "", "postcode": "63000", "country": ""})
set_place("  Thiers  ", 63300, "FR")
check("spaces removed, postal code written as a number accepted", agent.weather_place() == {"city": "Thiers", "postcode": "63300", "country": "FR"},
      agent.weather_place())
set_place("x" * 200, None, None)
check("long town: cut (80 characters)", len(agent.weather_place()["city"]) == 80)
for name in ("WEATHER_CITY", "WEATHER_POSTCODE", "WEATHER_COUNTRY"):
    delattr(cfg, name)
check("older config.py without these settings: no place, no crash", agent.weather_place() is None)


# --- register_device ---
async def registration():
    a = agent.TVControlAgent()
    sent = []

    async def capture(data):
        sent.append(data)

    a.send_message = capture
    set_place("Clermont-Ferrand", "63000", "France")
    await a.register_device()
    check("register_device: weatherPlace sent with the place", sent and sent[-1].get("weatherPlace") == {
        "city": "Clermont-Ferrand", "postcode": "63000", "country": "France"}, sent)
    set_place(None, None, None)
    await a.register_device()
    check("register_device without place: weatherPlace None", "weatherPlace" in sent[-1] and sent[-1]["weatherPlace"] is None)


asyncio.run(registration())

# --- Health report ---
set_place("Clermont-Ferrand", "63000", "France")
check("report: place set -> ok, the place shown",
      diagnostics.check_weather() == {"id": "weather", "status": "ok", "value": "Clermont-Ferrand 63000 France"}, diagnostics.check_weather())
set_place(None, None, None)
check("report: no place -> info", diagnostics.check_weather() == {"id": "weather", "status": "info", "value": "-"})
check("report: line translated (fr, en, es)", all(
    __import__("i18n").MESSAGES[lang].get("diag.check.weather") for lang in ("fr", "en", "es")))

real_config = (Path(__file__).resolve().parents[1] / "config.py").read_text(encoding="utf-8")
check("config.py: the three settings, None by default",
      all(f"\n{name} = None\n" in real_config for name in ("WEATHER_CITY", "WEATHER_POSTCODE", "WEATHER_COUNTRY")))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
