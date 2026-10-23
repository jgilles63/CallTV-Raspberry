# Settings changed on the TV (settings_store.py, voice_model.py, agent.py;
# ROADMAP 2.15) and "Robot, décroche" / "Robot, raccroche" while it rings.
# Checks: only a closed list of settings, each one checked (never code, never
# the server or the identity); settings.json applied at the end of config.py
# (a broken file never stops the Raspberry); the speech model of a new
# language downloaded and checked like install.sh (same table, SHA-256,
# archive opened in a temporary folder); agent: current settings sent,
# "Apply" saved, restart only when needed, refused during a call; spoken
# answer / decline only while it rings, ringtone turned down while the robot
# listens.
import asyncio
import hashlib
import io
import json
import re
import sys
import tempfile
import time
import types
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Raspberry_receiver/

cfg = types.ModuleType("config")
cfg.LANGUAGE = "fr"; cfg.RASPBERRY_ID = "rpi-settings"; cfg.DEVICE_SECRET = "secret"
cfg.SERVER_URL = "wss://x"; cfg.UNAUTHORIZED_RETRY_DELAY = 30; cfg.CALL_DURATION = 30
cfg.MOUSE_DEVICE = None; cfg.MOUSE_RETRY_DELAY = 5; cfg.BASE_DIR = Path(tempfile.mkdtemp())
cfg.CACHE_DIR = Path(tempfile.mkdtemp()); cfg.VOICE_VOLUME = 1.5; cfg.AUDIO_DEVICE = None
cfg.MAX_CALLER_NAME_LENGTH = 30; cfg.MAX_CACHED_CALLS = 5; cfg.RINGTONE_PATH = "x.wav"; cfg.RINGTONE_VOLUME = 0.2
cfg.WEATHER_CITY = "Madrid"; cfg.WEATHER_POSTCODE = "28051"; cfg.WEATHER_COUNTRY = "Espagne"
cfg.RADIO_STATIONS = [{"name": "France Inter", "frequency": 87.8, "url": "https://x/inter.mp3"}]
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

import settings_store as st  # noqa: E402
import voice_model  # noqa: E402
import voice_commands as v  # noqa: E402
import tts_audio  # noqa: E402
import agent  # noqa: E402

passed = failed = 0


def check(label, condition, detail=""):
    global passed, failed
    passed, failed = passed + bool(condition), failed + (not condition)
    print(f"{'OK ' if condition else 'KO '} {label} {detail}")


ROOT = Path(__file__).resolve().parents[1]

# --- Closed list of settings ---
check("valid settings kept", st.validate({"language": "es", "ringtoneLevel": 5, "city": "Saint-Étienne", "postcode": "42000",
                                          "country": "France"})
      == {"LANGUAGE": "es", "RINGTONE_VOLUME": 0.5, "WEATHER_CITY": "Saint-Étienne", "WEATHER_POSTCODE": "42000",
          "WEATHER_COUNTRY": "France"})
check("anything else ignored (server, identity, unknown language, level out of range)",
      st.validate({"language": "de", "ringtoneLevel": 11, "SERVER_URL": "wss://evil", "DEVICE_SECRET": "x", "serverUrl": "x"}) == {})
check("level must be a number 1 to 10 (not text, not true)",
      st.validate({"ringtoneLevel": "5"}) == {} and st.validate({"ringtoneLevel": True}) == {} and st.validate({"ringtoneLevel": 0}) == {})
cleaned = st.validate({"city": "Lyon\"; import os #" + "x" * 80})["WEATHER_CITY"]
check("place cleaned like install.sh (no quote, no ;, no #), cut", cleaned.startswith("Lyon import os")
      and not set('";#') & set(cleaned) and len(cleaned) <= 60
      and len(st.validate({"postcode": "1" * 40})["WEATHER_POSTCODE"]) == 12, cleaned)
check("empty place: None (no weather)", st.validate({"city": "  ", "country": None}) == {"WEATHER_CITY": None, "WEATHER_COUNTRY": None})
check("name of this TV: cleaned (no quote, no < >), 30 characters, empty -> None (name of the owner)",
      st.validate({"tvName": " Mamie \"<b>" + "x" * 40})["TV_NAME"] == "Mamie b" + "x" * 20
      and st.validate({"tvName": "  "}) == {"TV_NAME": None} and st.validate({"tvName": 5}) == {}
      and st.validate({"tvName": "Señora Pérez"}) == {"TV_NAME": "Señora Pérez"})
check("name of this TV kept in settings.json (checked again when read)",
      st.validate_saved({"TV_NAME": "Mamie"}) == {"TV_NAME"} and st.validate_saved({"TV_NAME": "Ma\"mie"}) == set())
check("not an object: nothing", st.validate("LANGUAGE=en") == {} and st.validate(None) == {})
check("ringtone volume <-> level", st.ringtone_level(0.2) == 2 and st.ringtone_level(1) == 10 and st.ringtone_level("x") == 2)
check("voice of the announcement: level 1 to 13, 10 = 100 % = 1.5 (volume of origin), 13 = 130 %",
      st.validate({"ringtoneVoiceLevel": 10}) == {"VOICE_VOLUME": 1.5} and st.validate({"ringtoneVoiceLevel": 13}) == {"VOICE_VOLUME": 1.95}
      and st.validate({"ringtoneVoiceLevel": 1}) == {"VOICE_VOLUME": 0.15} and st.validate({"ringtoneVoiceLevel": 14}) == {}
      and st.voice_level(1.5) == 10 and st.voice_level(1.95) == 13 and st.voice_level(9) == 13 and st.voice_level(None) == 10)
check("quiet hours: hours 0 to 23 only (not text, not true, not 24)",
      st.validate({"quietStart": 22, "quietEnd": 0}) == {"QUIET_START_HOUR": 22, "QUIET_END_HOUR": 0}
      and st.validate({"quietStart": 24, "quietEnd": "8"}) == {} and st.validate({"quietStart": True, "quietEnd": -1}) == {}
      and st.validate_saved({"QUIET_START_HOUR": 23, "QUIET_END_HOUR": 7.5}) == {"QUIET_START_HOUR"})
check("quiet hours over midnight (22 h to 8 h): 22 h to 7 h 59 silent, 8 h to 21 h 59 rings",
      all(st.in_quiet_hours(h, 22, 8) for h in (22, 23, 0, 3, 7)) and not any(st.in_quiet_hours(h, 22, 8) for h in (8, 12, 21)))
check("quiet hours in the day (13 h to 15 h) and same hour twice (never silent)",
      st.in_quiet_hours(13, 13, 15) and st.in_quiet_hours(14, 13, 15) and not st.in_quiet_hours(15, 13, 15)
      and not st.in_quiet_hours(12, 13, 15) and not any(st.in_quiet_hours(h, 7, 7) for h in range(24)))

base = Path(tempfile.mkdtemp())
check("no file: nothing", st.load(base) == {})
check("saved", st.save(base, {"LANGUAGE": "en", "WEATHER_CITY": "Lyon"}) and st.load(base) == {"LANGUAGE": "en", "WEATHER_CITY": "Lyon"})
st.save(base, {"RINGTONE_VOLUME": 0.7})
check("saved again: added to the file", st.load(base) == {"LANGUAGE": "en", "WEATHER_CITY": "Lyon", "RINGTONE_VOLUME": 0.7})
(base / st.FILE_NAME).write_text(json.dumps({"LANGUAGE": "en", "SERVER_URL": "wss://evil", "RINGTONE_VOLUME": 9,
                                             "WEATHER_CITY": "Lyon\"; x", "DEVICE_SECRET": "s"}))
check("file edited by hand: only the valid settings", st.load(base) == {"LANGUAGE": "en"}, st.load(base))
(base / st.FILE_NAME).write_text("{broken")
check("broken file: nothing", st.load(base) == {})
namespace = {"BASE_DIR": base, "LANGUAGE": "fr", "SERVER_URL": "wss://appelermami.fr"}
st.save(base, {"LANGUAGE": "es"})
st.apply(namespace)
check("apply: settings.json over config.py", namespace["LANGUAGE"] == "es" and namespace["SERVER_URL"] == "wss://appelermami.fr")

# config.py applies it at its end, and a broken file never stops it
config_text = (ROOT / "config.py").read_text(encoding="utf-8")
check("config.py: settings.json applied at its very end",
      config_text.rstrip().endswith('print(f"⚠️ settings.json not applied ({_error})")')
      and "_settings_store.apply(globals())" in config_text)
real = types.ModuleType("real_config")
real.__file__ = str(ROOT / "config.py")
home = Path(tempfile.mkdtemp())
(home / "AppelerMamie").mkdir()
(home / "AppelerMamie" / st.FILE_NAME).write_text(json.dumps({"LANGUAGE": "en", "WEATHER_CITY": "Leeds"}))
code = config_text.replace("Path.home()", f"Path(r'{home}')")
exec(compile(code, "config.py", "exec"), real.__dict__)
check("real config.py: language and place of the TV taken", real.LANGUAGE == "en" and real.WEATHER_CITY == "Leeds"
      and real.SERVER_URL.startswith("wss://"))

# --- Speech model of a new language (same table as install.sh) ---
install_text = (ROOT / "install.sh").read_text(encoding="utf-8")
table = dict(re.findall(r'\[(\w\w)\]="(\S+ \S+)"', install_text))
check("models and SHA-256: the same as install.sh", {k: " ".join(v_) for k, v_ in voice_model.MODELS.items()} == table, table)


def zip_of(files):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return data.getvalue()


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


name = voice_model.MODELS["en"][0]
good = zip_of({f"{name}/conf/model.conf": "x", f"{name}/am/final.mdl": "y"})
asked = []


def opener_of(data):
    def opener(url, timeout):
        asked.append(url)
        return FakeResponse(data)
    return opener


cfg.BASE_DIR = Path(tempfile.mkdtemp())
voice_model.MODELS["en"] = (name, hashlib.sha256(b"other").hexdigest())
check("file different from the known one: refused, nothing installed",
      voice_model.download("en", opener_of(good)) is False and not voice_model.model_dir().exists())
voice_model.MODELS["en"] = (name, hashlib.sha256(good).hexdigest())
check("expected file: model installed, its name kept", voice_model.download("en", opener_of(good)) is True
      and (voice_model.model_dir() / "conf" / "model.conf").exists() and voice_model.installed_name() == name
      and asked[-1].endswith(f"/{name}.zip"))
asked.clear()
check("already there: not downloaded again", voice_model.download("en", opener_of(good)) is True and asked == [])
evil = zip_of({"vosk-model-small-es-0.42/conf/x": "x", "vosk-model-small-es-0.42/../../evil.txt": "x"})
voice_model.MODELS["es"] = ("vosk-model-small-es-0.42", hashlib.sha256(evil).hexdigest())
check("archive with a path outside the model: refused, old model kept",
      voice_model.download("es", opener_of(evil)) is False and voice_model.installed_name() == name
      and not (cfg.BASE_DIR.parent / "evil.txt").exists())
check("no temporary folder left", not any(p.name.startswith(".vosk-") for p in cfg.BASE_DIR.iterdir()))
check("unknown language: nothing", voice_model.download("de", opener_of(good)) is False)


def broken_opener(url, timeout):
    raise OSError("no internet")


voice_model.MODELS["fr"] = ("vosk-model-small-fr-0.22", "0" * 64)
check("no internet: False, no crash, old model kept", voice_model.download("fr", broken_opener) is False
      and voice_model.installed_name() == name)


# --- Agent: settings page ---
async def registration(a):
    """Registration message the agent sends to the server."""
    captured = []
    previous = a.send_message

    async def capture(data):
        captured.append(data)

    a.send_message = capture
    await a.register_device()
    a.send_message = previous
    return captured[-1]


async def agent_settings():
    a = agent.TVControlAgent()
    sent = []

    async def capture(data):
        sent.append(data)

    a.send_message = capture
    a.registered = True
    cfg.BASE_DIR = Path(tempfile.mkdtemp())
    await a.handle_message({"type": "settings_request"})
    check("settings asked: current values and the radio stations (not changed there)", sent[-1] == {
        "type": "settings", "values": {"language": "fr", "ringtoneLevel": 2, "ringtoneVoiceLevel": 10,
                                       "radioLevel": 2, "robotVoiceLevel": 8, "quietStart": 22, "quietEnd": 8, "city": "Madrid",
                                       "postcode": "28051", "country": "Espagne", "tvName": ""},
        "stations": [{"name": "France Inter", "frequency": "87.8"}]}, sent[-1])

    restarts = []
    a.restart_agent = lambda: restarts.append(True)
    agent.SETTINGS_RESTART_DELAY = 0
    downloads = []
    voice_model.download = lambda lang: downloads.append(lang) or True

    sent.clear()
    await a.apply_settings({"ringtoneLevel": 5, "ringtoneVoiceLevel": 12, "city": "Madrid"})
    check("only the volumes of the ringtone (music, voice) changed: saved, used at once, no restart",
          cfg.RINGTONE_VOLUME == 0.5 and cfg.VOICE_VOLUME == 1.8 and st.load(cfg.BASE_DIR) == {"RINGTONE_VOLUME": 0.5, "VOICE_VOLUME": 1.8}
          and restarts == []
          and sent == [{"type": "settings_applied", "ok": True, "restart": False, "language": "fr", "voiceModel": True}], sent)
    sent.clear()
    await a.apply_settings({"quietStart": 21, "quietEnd": 7})
    check("quiet hours changed: saved, used at once, no restart",
          cfg.QUIET_START_HOUR == 21 and cfg.QUIET_END_HOUR == 7 and st.load(cfg.BASE_DIR)["QUIET_START_HOUR"] == 21
          and restarts == [] and sent[-1]["restart"] is False and a.current_settings()["quietEnd"] == 7, sent)
    sent.clear()
    await a.apply_settings({"city": "Lyon", "postcode": "69001", "country": "France", "SERVER_URL": "wss://evil"})
    check("place changed: saved, agent restarted (new place sent to the server), server never changed",
          st.load(cfg.BASE_DIR)["WEATHER_CITY"] == "Lyon" and "SERVER_URL" not in st.load(cfg.BASE_DIR)
          and restarts == [True] and sent[-1]["restart"] is True and downloads == [], sent)
    sent.clear()
    restarts.clear()
    await a.apply_settings({"tvName": "Mamie"})
    check("name of this TV changed: saved, agent restarted (the new name sent to the server)",
          st.load(cfg.BASE_DIR)["TV_NAME"] == "Mamie" and cfg.TV_NAME == "Mamie" and restarts == [True], sent)
    check("... given to the server at the registration", (await registration(a))["tvName"] == "Mamie")
    cfg.TV_NAME = None
    sent.clear()
    restarts.clear()
    await a.apply_settings({"language": "es"})
    check("language changed: speech model of the language asked first, then restart",
          downloads == ["es"] and sent[0] == {"type": "settings_progress", "step": "voiceModel"}
          and sent[-1]["language"] == "es" and sent[-1]["voiceModel"] is True and restarts == [True], sent)
    sent.clear()
    restarts.clear()
    await a.apply_settings({"language": "es", "city": "Lyon"})
    check("nothing different: nothing saved, no restart", sent == [{"type": "settings_applied", "ok": True, "restart": False}]
          and restarts == [])
    tts = agent.tts_audio
    tts.save_radio_volume(37)
    sent.clear()
    await a.apply_settings({"radioLevel": 4, "robotVoiceLevel": 6, "language": "es", "city": "Lyon"})
    check("volume of the radio unchanged on the page (level 4 = its 37 %): its exact volume kept; voice of the robot 6",
          tts.radio_volume() == 37 and tts.voice_level() == 6 and restarts == []
          and sent == [{"type": "settings_applied", "ok": True, "restart": False}], sent)
    sent.clear()
    await a.apply_settings({"radioLevel": 7, "robotVoiceLevel": 6})
    check("volume of the radio changed (7): 70 %, the radio page told, no restart",
          tts.radio_volume() == 70 and any(m["type"] == "radio_state" and m["volume"] == 70 for m in sent) and restarts == [], sent)
    await a.apply_settings({"radioLevel": 0})
    check("radio level 0: silent (0 %)", tts.radio_volume() == 0)
    for bad in ({"radioLevel": 11}, {"robotVoiceLevel": 0}, {"robotVoiceLevel": True}, {"radioLevel": "5"}):
        await a.apply_settings(bad)
    check("strange volumes: refused", tts.radio_volume() == 0 and tts.voice_level() == 6)
    check("validate_volumes: known volumes only", st.validate_volumes({"radioLevel": 3, "robotVoiceLevel": 10, "x": 1}) ==
          {"radioLevel": 3, "robotVoiceLevel": 10} and st.validate_volumes(None) == {})
    a.call_window, a.current_call_id = True, "c1"
    sent.clear()
    await a.apply_settings({"city": "Paris", "robotVoiceLevel": 2})
    check("during a call (or ringing): refused", sent == [{"type": "settings_applied", "ok": False, "reason": "call"}]
          and st.load(cfg.BASE_DIR)["WEATHER_CITY"] == "Lyon" and agent.tts_audio.voice_level() == 6)
    a.call_window, a.current_call_id = False, None
    cfg.LANGUAGE = "fr"


asyncio.run(agent_settings())


# --- "Robot, décroche" / "Robot, raccroche" while it rings ---
def result(*words):
    return {"result": [{"word": w, "conf": 0.95} for w in words], "text": " ".join(words)}


for words_heard, lang, wanted in (
        (("robot", "décroche"), "fr", "answer"), (("décroche", "robot"), "fr", "answer"), (("robot", "réponds"), "fr", "answer"),
        (("robot", "raccroche"), "fr", "decline"), (("robot", "refuse"), "fr", "decline"),
        (("robot", "pick", "up"), "en", "answer"), (("robot", "hang", "up"), "en", "decline"),
        (("robot", "contesta"), "es", "answer"), (("robot", "cuelga"), "es", "decline")):
    check(f"{' '.join(words_heard)} ({lang}): {wanted}", v.command_of(result(*words_heard), lang) == wanted)


async def agent_ringing():
    a = agent.TVControlAgent()
    sent, volumes = [], []

    async def capture(data):
        sent.append(data)

    a.send_message = capture
    a.registered = True
    a.alert_sound = types.SimpleNamespace(play=lambda name=None: None, stop=lambda: None)
    tts_audio.find_ringing_card = lambda: {"id": "AUDIO"}
    tts_audio.set_card_volume = lambda card, percent, mapped=False: volumes.append(percent)
    tts_audio.set_max_volume = lambda card: volumes.append(100)

    await a.on_voice_command("answer")
    check("\"décroche\" outside a ringing call: nothing", sent == [] and a.active_call_id is None)
    a.call_window, a.current_call_id = True, "ring-1"
    check("while it rings: the microphone is listened to", a.should_listen_sound() is True)
    await a.on_voice_command(v.LISTENING)
    check("\"robot\" heard while it rings: green, ringtone silent while the robot listens",
          {"type": "voice_command", "command": "listening"} in sent and volumes[-1] == 0)
    await a.on_voice_command(v.LISTENING_OFF)
    check("nothing said: the ringtone back", volumes[-1] == 100)
    await a.on_voice_command("time")
    check("other commands while it rings: ignored", not any(m.get("command") == "time" for m in sent))
    await a.on_voice_command("answer")
    check("\"Robot, décroche\": the call is answered (accept_call), ringtone back to its volume",
          {"type": "accept_call", "callId": "ring-1"} in sent and a.active_call_id == "ring-1" and volumes[-1] == 100, sent)
    check("then, during the conversation: the microphone is not listened to", a.should_listen_sound() is False)
    sent.clear()
    await a.on_voice_command("decline")
    check("\"raccroche\" during the conversation: nothing (only while it rings)", sent == [])
    a.active_call_id = None
    a.call_window, a.current_call_id = True, "ring-2"
    await a.on_voice_command("decline")
    check("\"Robot, raccroche\" while it rings: declined (hangup)", sent == [{"type": "hangup", "callId": "ring-2"}]
          and not a.call_window, sent)


asyncio.run(agent_ringing())


# --- Quiet hours: a call shown on the TV without ringtone ---
async def agent_quiet_hours():
    a = agent.TVControlAgent()
    sent, played = [], []

    async def capture(data):
        sent.append(data)

    a.send_message = capture
    a.registered = True
    a.loop = asyncio.get_running_loop()
    a.alert_sound = types.SimpleNamespace(play=lambda name=None: played.append(name), stop=lambda: None)
    real_datetime = agent.datetime
    cfg.QUIET_START_HOUR, cfg.QUIET_END_HOUR = 22, 8

    async def call_at(hour, call_id):
        agent.datetime = types.SimpleNamespace(datetime=types.SimpleNamespace(now=lambda: types.SimpleNamespace(hour=hour)))
        sent.clear()
        played.clear()
        await a.handle_message({"type": "incoming_call", "callId": call_id, "callerName": "Paul"})
        for _ in range(50):
            if any(m["type"] == "sound_started" for m in sent):
                break
            await asyncio.sleep(0.02)
        if a.call_timeout_task:
            a.call_timeout_task.cancel()
        a.call_window, a.current_call_id = False, None

    try:
        await call_at(23, "night-1")
        check("call at 23 h (quiet hours 22 h to 8 h): no ringtone nor announcement, but shown and timed as usual",
              played == [] and {"type": "sound_started", "callId": "night-1"} in sent, (played, sent))
        await call_at(7, "night-2")
        check("call at 7 h: still silent", played == [])
        await call_at(8, "day-1")
        check("call at 8 h: the ringtone and the announcement as usual",
              played == ["Paul"] and {"type": "sound_started", "callId": "day-1"} in sent, (played, sent))
        cfg.QUIET_START_HOUR = cfg.QUIET_END_HOUR = 8
        await call_at(23, "same-hour")
        check("same hour twice: it always rings", played == ["Paul"])
        del cfg.QUIET_START_HOUR, cfg.QUIET_END_HOUR
        await call_at(23, "older-config")
        check("config.py without the quiet hours (older one): 22 h to 8 h", played == [])
    finally:
        agent.datetime = real_datetime


asyncio.run(agent_quiet_hours())


# --- While it rings: partial results read (the ringtone never stops) ---
class RingRecognizer:
    def __init__(self, model, rate, grammar):
        self.partial, self.resets = [], 0

    def SetWords(self, on):
        pass

    def SetPartialWords(self, on):
        self.partial_words = on

    def AcceptWaveform(self, data):
        return False

    def PartialResult(self):
        return json.dumps({"partial": " ".join(w for w, _c in self.partial),
                           "partial_result": [{"word": w, "conf": c} for w, c in self.partial]})

    def Reset(self):
        self.resets += 1


SILENCE = bytes(3200)
cfg.BASE_DIR = Path(tempfile.mkdtemp())
(cfg.BASE_DIR / "vosk-model" / "conf").mkdir(parents=True)
ringing = {"on": True}
voice = v.VoiceCommands(loader=lambda path: (object(), RingRecognizer))
voice.is_ringing = lambda: ringing["on"]
voice.start()
rec = voice.recognizer
check("confidence of the partial words asked", rec.partial_words is True)
rec.partial = [("es", 0.6), ("paul", 1.0), ("llama", 0.9)]
check("announcement of the ringtone heard: nothing", voice.frame(SILENCE, True) is None)
rec.partial = [("temps", 0.45), ("robot", 0.98)]
check("\"robot\" (sure) in the partial result: green at once (ringtone turned down)", voice.frame(SILENCE, True) == v.LISTENING)
check("... only once", voice.frame(SILENCE, True) is None)
rec.partial = [("temps", 0.45), ("robot", 0.98), ("[unk]", 1.0), ("décroche", 0.9)]
check("then \"décroche\" at the end (after robot): answer at once, recognizer started again",
      voice.frame(SILENCE, True) == "answer" and rec.resets == 1 and not voice.listening)
voice.green_shown, voice.listening_until = True, time.monotonic() + 5
rec.partial = [("[unk]", 1.0), ("décroche", 0.8), ("[unk]", 0.9)]
check("after the green, \"décroche\" with a noise after it: answer", voice.frame(SILENCE, True) == "answer")
rec.partial = [("robot", 1.0), ("raccroche", 0.95)]
check("\"robot raccroche\" in one go: decline", voice.frame(SILENCE, True) == "decline")
rec.partial = [("raccroche", 0.95)]
check("\"raccroche\" without robot: nothing", voice.frame(SILENCE, True) is None)
rec.partial = [("robot", 0.5), ("décroche", 0.3)]
check("not sure enough: nothing", voice.frame(SILENCE, True) is None)
rec.partial = [("robot", 1.0), ("quelle", 1.0), ("heure", 1.0)]
voice.green_shown, voice.listening_until = True, time.monotonic() + 5
check("other commands in the partial result while it rings: not taken", voice.frame(SILENCE, True) is None)
voice.green_shown, voice.listening_until = False, 0.0
rec.partial = [("robot", 0.98)]
voice.frame(SILENCE, True)
rec.partial = [("robot", 0.98), ("[unk]", 1.0)]
voice.listening_until = 0.0
check("green while it rings, nothing asked: off when the time is over (the sound never stops)",
      voice.frame(SILENCE, True) == v.LISTENING_OFF and not voice.green_shown)
rec.final_words = [("es", 0.6), ("paul", 1.0), ("robot", 1.0), ("contesta", 0.8), ("[unk]", 1.0)]
voice.lang = "es"
voice.table = v.phrase_table("es")
check("final result while it rings, noise of the ringtone around (Spanish): \"robot contesta\" found in it", voice._ringing_check(rec.final_words, final=True) == "answer")
voice.lang, voice.table = "fr", v.phrase_table("fr")
ringing["on"] = False
voice.green_shown = False
rec.partial = [("robot", 1.0), ("décroche", 1.0)]
check("outside the ringing: partial results not read (as before)", voice.frame(SILENCE, True) is None)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
