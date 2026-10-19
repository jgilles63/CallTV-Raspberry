# Spoken commands to the robot (voice_commands.py, ROADMAP 2.13 level 2).
# Vosk is simulated: results like the real small French model gave on a real
# Pi on 18/10/2026 ("robot bonjour", "bonjour robot", and single words in
# ordinary sentences). Checks: grammar, a command only for the wake word next
# to the word of the command (both orders, enough confidence), recognizer fed
# only while a sound is heard (plus the half second before), result at the
# end of the sound, muted while the robot speaks, model loaded / unloaded,
# missing model; the frames of sound_level.py go to it; agent: voice_command
# sent, answer said, not during a call, not twice in a row; the sentence of
# the robot (tts_audio.say).
import asyncio
import array
import json
import sys
import time
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Raspberry_receiver/

cfg = types.ModuleType("config")
cfg.LANGUAGE = "fr"; cfg.RASPBERRY_ID = "rpi-voice"; cfg.DEVICE_SECRET = "secret"
cfg.SERVER_URL = "wss://x"; cfg.UNAUTHORIZED_RETRY_DELAY = 30; cfg.CALL_DURATION = 30
cfg.MOUSE_DEVICE = None; cfg.MOUSE_RETRY_DELAY = 5; cfg.BASE_DIR = Path(tempfile.mkdtemp())
cfg.CACHE_DIR = Path(tempfile.mkdtemp()); cfg.VOICE_VOLUME = 1.5; cfg.AUDIO_DEVICE = None
cfg.MAX_CALLER_NAME_LENGTH = 30; cfg.MAX_CACHED_CALLS = 5; cfg.RINGTONE_PATH = "x.wav"; cfg.RINGTONE_VOLUME = 0.2
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

import voice_commands as v  # noqa: E402
import sound_level  # noqa: E402
import tts_audio  # noqa: E402
import agent  # noqa: E402

passed = failed = 0


def check(label, condition, detail=""):
    global passed, failed
    passed, failed = passed + bool(condition), failed + (not condition)
    print(f"{'OK ' if condition else 'KO '} {label} {detail}")


def result(*words, conf=0.95):
    return {"result": [{"word": w, "conf": conf} for w in words], "text": " ".join(words)}


# --- Grammar and commands ---
g = json.loads(v.grammar("fr"))
check("French grammar: each command with the wake word before or after, alone; the wake word; anything else",
      {"robot bonjour", "bonjour robot", "bonjour", "robot quelle heure est il", "quelle heure est il robot",
       "robot quel temps fait il", "quel temps fait il robot", "robot", "[unk]"} <= set(g), g)
check("English and Spanish words", "robot hello" in v.grammar("en") and "hola robot" in v.grammar("es")
      and "robot what time is it" in v.grammar("en") and "robot qué tiempo hace" in v.grammar("es"))
check("accents written as they are (Vosk does not read \\u00e9)", "qué" in v.grammar("es") and "\\u" not in v.grammar("es"))
for words_heard, lang, wanted in (
        (("robot", "quelle", "heure", "est", "il"), "fr", "time"),
        (("quelle", "heure", "est", "il", "robot"), "fr", "time"),
        (("robot", "quelle", "heure"), "fr", "time"),
        (("robot", "quel", "temps", "fait", "il"), "fr", "weather"),
        (("quel", "temps", "fait", "il", "robot"), "fr", "weather"),
        (("robot", "what", "time", "is", "it"), "en", "time"),
        (("robot", "what", "is", "the", "weather"), "en", "weather"),
        (("robot", "qué", "hora", "es"), "es", "time"),
        (("qué", "tiempo", "hace", "robot"), "es", "weather"),
        (("robot", "[unk]", "heure"), "fr", None),
        (("quelle", "heure", "est", "il"), "fr", None),
        (("robot", "bonjour", "quel"), "fr", "hello")):
    check(f"{' '.join(words_heard)} ({lang}): {wanted}", v.command_of(result(*words_heard), lang) == wanted)
check("\"robot bonjour\": hello", v.command_of(result("robot", "bonjour"), "fr") == "hello")
check("\"bonjour robot\": hello", v.command_of(result("bonjour", "robot"), "fr") == "hello")
check("said three times in one breath: hello", v.command_of(result("robot", "bonjour", "robot", "bonjour"), "fr") == "hello")
check("\"bonjour\" alone (ordinary sentence): nothing", v.command_of(result("bonjour"), "fr") is None)
check("\"robot\" alone or with an unknown word: nothing",
      v.command_of(result("robot"), "fr") is None and v.command_of(result("robot", "[unk]"), "fr") is None)
check("words apart (\"robot [unk] bonjour\"): nothing", v.command_of(result("robot", "[unk]", "bonjour"), "fr") is None)
check("low confidence: nothing", v.command_of(result("robot", "bonjour", conf=0.3), "fr") is None)
real = {"result": [{"conf": 1.0, "word": "robot"}, {"conf": 0.514782, "word": "bonjour"}], "text": "robot bonjour"}
check("real command of a real Pi (\"bonjour\" at 0.51): hello", v.command_of(real, "fr") == "hello")
check("words of the previous result: \"robot\" then \"bonjour\" -> hello",
      v.command_of(result("bonjour"), "fr", before=[("robot", 0.97)]) == "hello")
check("Spanish: \"robot hola\"", v.command_of(result("robot", "hola"), "es") == "hello")
check("empty or broken result: nothing", v.command_of({}, "fr") is None and v.command_of({"result": [None, 3]}, "fr") is None)
# Commands nobody asked (TV of the user, 19/10/2026: "radio 0.82 robot 0.70" turned the radio on)
unasked = {"result": [{"conf": 0.82, "word": "radio"}, {"conf": 0.70, "word": "robot"}], "text": "radio robot"}
check("real mistake of the TV (weak \"robot\" 0.70 after \"radio\"): nothing", v.command_of(unasked, "fr") is None)
check("weak \"robot\" before the command: nothing",
      v.command_of({"result": [{"word": "robot", "conf": 0.7}, {"word": "bonjour", "conf": 0.9}]}, "fr") is None)
check("sure \"robot\" (0.8 and more): taken",
      v.command_of({"result": [{"word": "robot", "conf": 0.8}, {"word": "bonjour", "conf": 0.6}]}, "fr") == "hello")
check("\"robot quelle heure\" with 2 other words around (s'il te plait): taken",
      v.command_of(result("[unk]", "robot", "quelle", "heure", "[unk]"), "fr") == "time")
check("... in a long sentence (3 other words and more): nothing",
      v.command_of(result("[unk]", "[unk]", "robot", "quelle", "heure", "[unk]"), "fr") is None
      and v.command_of(result("[unk]", "radio", "robot", "[unk]", "[unk]", "bonjour"), "fr") is None)
check("while it rings: any number of other words (the ringtone is heard all the time)",
      v.command_of(result("[unk]", "[unk]", "[unk]", "robot", "bonjour", "[unk]"), "fr", max_others=None) == "hello")


# --- Recognizer fed with the frames ---
class FakeRecognizer:
    instances = []

    def __init__(self, model, rate, grammar):
        self.model, self.rate, self.grammar = model, rate, grammar
        self.fed, self.words, self.resets, self.final = [], False, 0, result()
        self.partial = None
        # Partial result (the sentence goes on), {"partial": "robot quelle"}
        self.partial_text = ""
        FakeRecognizer.instances.append(self)

    def SetWords(self, on):
        self.words = on

    def AcceptWaveform(self, data):
        self.fed.append(data)
        return self.partial is not None

    def Result(self):
        r, self.partial = self.partial, None
        return json.dumps(r)

    def FinalResult(self):
        return json.dumps(self.final)

    def PartialResult(self):
        return json.dumps({"partial": self.partial_text})

    def Reset(self):
        self.resets += 1


loads = []


def fake_loader(path):
    loads.append(path)
    return object(), FakeRecognizer


def frame(n):
    return bytes([n % 256]) * 3200


cfg.BASE_DIR = Path(tempfile.mkdtemp())
voice = v.VoiceCommands(loader=fake_loader)
voice.start()
check("no model installed: not loaded, no crash", not voice.ready and loads == [])
(cfg.BASE_DIR / "vosk-model" / "conf").mkdir(parents=True)
voice.start()
rec = FakeRecognizer.instances[-1]
check("model installed: loaded, 16 kHz, closed grammar, words with confidence",
      voice.ready and rec.rate == 16000 and json.loads(rec.grammar) == g and rec.words is True)

for i in range(10):
    voice.frame(frame(i), False)
check("quiet: nothing given to the recognizer (no processor used)", rec.fed == [])
rec.final = result("robot", "bonjour")
got = voice.frame(frame(10), True)
check("a sound starts: the half second before it is given too (start of \"robot\" not cut)",
      rec.fed == [frame(i) for i in range(4, 11)] and got is None, len(rec.fed))
got = [voice.frame(frame(11 + i), True) for i in range(5)]
check("while the sound lasts: frames given", len(rec.fed) == 12 and got == [None] * 5)
got = [voice.frame(frame(20 + i), False) for i in range(v.TAIL_FRAMES)]
check("sound over (0.8 s later): final result -> hello", got[-1] == "hello" and got[:-1] == [None] * (v.TAIL_FRAMES - 1), got)
before = len(rec.fed)
voice.frame(frame(40), False)
check("then quiet again: nothing given", len(rec.fed) == before)
rec.partial = result("bonjour", "robot")
check("result in the middle of a sound: hello at once", voice.frame(frame(41), True) == "hello")
voice.mute(30)
check("muted (the robot speaks): nothing given, its own voice is not heard",
      voice.frame(frame(42), True) is None and voice.frame(frame(43), True) is None and rec.resets == 1)
voice.muted_until = 0
rec.final = result("bonjour")
for i in range(v.TAIL_FRAMES + 3):
    voice.frame(frame(50 + i), i < 2)
check("ordinary sentence with \"bonjour\": nothing", True)

# A short pause splits "robot ... bonjour" into two results (seen on a real Pi)
voice.muted_until = 0
voice.last_words = []
rec.partial = result("robot")
check("\"robot\" alone in a result: the robot listens (green), no command yet", voice.frame(frame(60), True) == v.LISTENING)
rec.partial = result("bonjour")
check("\"bonjour\" in the next result: hello", voice.frame(frame(61), True) == "hello")
check("command heard: no longer listening", not voice.listening and not voice.green_shown)
log_lines = (cfg.BASE_DIR / v.LOG_FILE_NAME).read_text(encoding="utf-8").splitlines()
check("voice.log: what the robot heard and did (kept after a restart), with the time",
      log_lines[-1].endswith("Heard: bonjour 0.95 -> hello") and "\"Robot\" heard (robot 0.95)" in log_lines[-2]
      and log_lines[-1][:4].isdigit(), log_lines[-2:])
old_base = cfg.BASE_DIR
cfg.BASE_DIR = Path(tempfile.mkdtemp())
for n in range(v.LOG_LINES + 20):
    v.log(f"line {n}")
log_lines = (cfg.BASE_DIR / v.LOG_FILE_NAME).read_text(encoding="utf-8").splitlines()
check("voice.log: last LOG_LINES lines only", len(log_lines) == v.LOG_LINES and log_lines[-1].endswith(f"line {v.LOG_LINES + 19}"))
cfg.BASE_DIR = cfg.BASE_DIR / "missing"
v.log("folder missing: no crash")
cfg.BASE_DIR = old_base
rec.partial = result("robot")
voice.frame(frame(62), True)
voice.last_word_at -= 10
voice.listening_until = time.monotonic() - 1
rec.partial = result("bonjour")
check("\"bonjour\" long after \"robot\" (ordinary sentences): no command", voice.frame(frame(63), True) is None)

# "Robot" alone, then the question alone while the robot is green
voice.muted_until = 0
voice.last_words, voice.listening_until, voice.green_shown = [], 0.0, False
rec.partial_text = "robot"
check("\"robot\" only guessed in the partial result (ordinary sentence): not green", voice.frame(frame(70), True) is None
      and not voice.green_shown)
rec.partial_text = ""
rec.partial = result("robot")
check("sure \"robot\" at the end of the sentence: green, listening", voice.frame(frame(72), True) == v.LISTENING and voice.listening)
rec.partial = result("robot")
check("... green sent only once", voice.frame(frame(71), True) is None)
voice.last_words = []
rec.partial = result("quelle", "heure", "est", "il")
check("question alone while green: time", voice.frame(frame(73), True) == "time")
check("... then not green any more (the answer pose replaces it)", not voice.green_shown and not voice.listening)
voice.last_words = []
rec.partial = result("quelle", "heure", "est", "il")
check("the same question without \"robot\" before: nothing", voice.frame(frame(74), True) is None)

# Green, then something else said (a conversation): green off at once
for heard_then, label in ((("[unk]", "heure"), "\"heure\" in an ordinary sentence (\"cet après-midi\")"),
                          (("temps",), "\"temps\" alone (\"en même temps\")"),
                          (("quel", "temps", "fait"), "not exactly a phrase"),
                          (("[unk]",), "anything else")):
    voice.last_words = []
    rec.partial = result("robot")
    voice.frame(frame(64), True)
    rec.partial = result(*heard_then)
    check(f"while green, {label}: no command, green off at once",
          voice.frame(frame(65), True) == v.LISTENING_OFF and not voice.listening)
    rec.partial = result("quel", "temps", "fait", "il")
    check("... then the question alone: nothing any more", voice.frame(frame(66), True) is None)
voice.last_words = []
rec.partial = result("robot")
voice.frame(frame(67), True)
rec.partial = result("quel", "temps")
check("while green, \"quel temps\": weather", voice.frame(frame(68), True) == "weather")

# Green, then nothing asked: off after the time
voice.last_words = []
rec.partial = result("robot")
voice.frame(frame(75), True)
voice.feeding = False
voice.listening_until = time.monotonic() - 1
check("no question in time: green off (quiet)", voice.frame(frame(77), False) == v.LISTENING_OFF)
check("... only once", voice.frame(frame(78), False) is None)

# Not sure enough to turn green
voice.last_words = []
rec.partial = result("robot", conf=0.7)
check("\"robot\" with a confidence under 0.8: not green", voice.frame(frame(82), True) is None and not voice.listening)
voice.last_words = []
rec.partial = result("robot", conf=0.82)
check("\"robot\" said from far (0.82, big room): green", voice.frame(frame(85), True) == v.LISTENING)
voice.mute(0)
voice.muted_until = 0
voice.last_words = []
rec.partial = result("[unk]", "robot", "[unk]")
check("\"robot\" inside an ordinary sentence ([unk] around): not green", voice.frame(frame(83), True) is None and not voice.listening)
voice.last_words = []
rec.partial = {"result": [{"word": "robot", "conf": 0.75}, {"word": "robot", "conf": 0.9}], "text": "robot robot"}
check("\"robot robot\" (seen on the Pi in a conversation): not green", voice.frame(frame(84), True) is None and not voice.listening)
voice.mute(1)
check("muted (the robot speaks): not listening any more", not voice.listening and not voice.green_shown)
voice.muted_until = 0

voice.stop()
check("stop (a call): model unloaded", not voice.ready and voice.model is None)
voice.start()
check("start again after the call: loaded again", voice.ready and len(loads) == 2)
cfg.VOICE_COMMANDS = False
voice.stop()
voice.start()
check("VOICE_COMMANDS = False: never loaded", not voice.ready and len(loads) == 2)
del cfg.VOICE_COMMANDS


def broken_loader(path):
    raise RuntimeError("vosk missing")


broken = v.VoiceCommands(loader=broken_loader)
broken.start()
check("Vosk missing or broken model: no voice commands, no crash", not broken.ready)


# --- The frames of sound_level.py go to the recognizer ---
def pcm(amplitude):
    return array.array("h", [amplitude, -amplitude] * (sound_level.FRAME_SAMPLES // 2)).tobytes()


async def through_sound_level():
    path = Path(tempfile.mkdtemp(), "mic.raw")
    path.write_bytes(b"".join(pcm(a) for a in [5000, 900] + [400] * 28 + [3000] * 10 + [400] * 20))
    sound_level.RECORD_COMMAND = [sys.executable, "-c", f"import sys; sys.stdout.buffer.write(open({str(path)!r}, 'rb').read())"]
    voice2 = v.VoiceCommands(loader=fake_loader)
    commands = []
    changes = []

    async def on_change(active):
        changes.append(active)

    async def on_command(name):
        commands.append(name)

    FakeRecognizer.instances.clear()
    await sound_level.listen_once(on_change, lambda: True, voice2, on_command)
    rec2 = FakeRecognizer.instances[-1]
    # 1 s of voice + 0.6 s before + 1.5 s until the end of the sound + 0.8 s after: about 4 s, not the whole 6 s
    check("sound_level: model loaded when the listening starts, given the frames around the voice only",
          20 <= len(rec2.fed) <= 40, len(rec2.fed))
    check("sound_level: nothing recognized, no command", commands == [], commands)
    check("sound_level: model unloaded when the listening stops", not voice2.ready)

asyncio.run(through_sound_level())


# --- Agent ---
async def agent_behaviour():
    a = agent.TVControlAgent()
    sent, said = [], []

    async def capture(data):
        sent.append(data)

    a.send_message = capture
    texts = []
    tts_audio.spoken_wav = lambda key: said.append(key) or "hello.wav"
    tts_audio.text_wav = lambda text: texts.append(text) or "now.wav"
    tts_audio.wav_seconds = lambda wav: 2.34
    tts_audio.play_wav = lambda wav: said.append(("play", wav)) or True
    a.registered = True
    await a.on_voice_command("hello")
    check("command heard: the robot stops listening at once (it must not hear itself)", a.voice.muted_until - time.monotonic() > 30)
    await a.voice_answer_task
    check("\"Robot bonjour\": voice_command sent with the length of the answer, fixed sentence said",
          sent == [{"type": "voice_command", "command": "hello", "seconds": 2.3}] and said == ["voice.hello", ("play", "hello.wav")], (sent, said))
    check("after its answer: listening again a moment later", a.voice.muted_until - time.monotonic() < 5)
    await a.on_voice_command("hello")
    check("said again at once: ignored (once every few seconds)", len(sent) == 1)
    a.last_voice_command_at = 0
    a.active_call_id = "call-1"
    await a.on_voice_command("hello")
    check("during a call: ignored", len(sent) == 1)
    a.active_call_id = None
    await a.on_voice_command("unknown")
    check("unknown command: ignored", len(sent) == 1)
    await a.on_voice_command(v.LISTENING)
    await a.on_voice_command(v.LISTENING_OFF)
    check("\"robot\" heard / no question: green on / off sent (not rate limited)",
          sent[1:] == [{"type": "voice_command", "command": "listening"}, {"type": "voice_command", "command": "listening_off"}], sent)
    a.active_call_id = "call-1"
    await a.on_voice_command(v.LISTENING)
    check("green during a call: never sent", len(sent) == 3)
    a.active_call_id = None
    del sent[1:]

    # "Robot, quelle heure est-il ?"
    sent.clear(); said.clear()
    a.last_voice_command_at = 0
    await a.on_voice_command("time")
    await a.voice_answer_task
    check("time: the time said (made now), the robot looks clever while it speaks",
          texts and texts[-1].startswith("Il est ") and sent == [{"type": "voice_command", "command": "time", "seconds": 2.3}]
          and said == [("play", "now.wav")], (texts, sent))

    # "Robot, quel temps fait-il ?": the weather is asked to the server
    sent.clear(); texts.clear()
    a.last_voice_command_at = 0
    await a.on_voice_command("weather")
    for _ in range(200):
        if sent:
            break
        await asyncio.sleep(0.01)
    check("weather: asked to the server with the hours (what is left of the day)",
          sent == [{"type": "weather_request", "hours": True}], sent)
    await a.handle_message({"type": "weather", "available": True, "temperature": 16.6, "place": "Madrid",
                            "today": {"icon": "rain", "min": 8, "max": 18, "rain": 70}})
    await a.voice_answer_task
    check("weather: temperature and forecast of the day said",
          texts == ["Il fait 17 degrés à Madrid. Aujourd'hui : de la pluie, entre 8 et 18 degrés. Risque de pluie : 70 pour cent."]
          and sent[-1] == {"type": "voice_command", "command": "weather", "seconds": 2.3}, (texts, sent))
    sent.clear(); texts.clear()
    a.last_voice_command_at = 0
    agent.WEATHER_ANSWER_TIMEOUT = 0.2
    await a.on_voice_command("weather")
    await a.voice_answer_task
    check("weather: no answer of the server -> \"I do not know the weather\"",
          texts == ["Je ne connais pas la météo pour le moment."], texts)
    a.last_voice_command_at = 0
    tts_audio.text_wav = lambda text: None
    sent.clear()
    await a.on_voice_command("time")
    await a.voice_answer_task
    check("answer not generated (no internet): the robot still moves, no crash, listening again",
          sent == [{"type": "voice_command", "command": "time"}] and a.voice.muted_until - time.monotonic() < 5, sent)

asyncio.run(agent_behaviour())


# --- Sentences of the answers ---
import datetime  # noqa: E402
import robot_answers as r  # noqa: E402
day = lambda h, m: datetime.datetime(2026, 10, 18, h, m)  # noqa: E731
check("time (fr): \"Il est 14 heures et 35 minutes.\"", r.time_sentence(day(14, 35), "fr") == "Il est 14 heures et 35 minutes.")
check("time (fr): singular, minuit, midi, pile",
      r.time_sentence(day(1, 1), "fr") == "Il est 1 heure et 1 minute." and r.time_sentence(day(0, 5), "fr") == "Il est minuit et 5 minutes."
      and r.time_sentence(day(12, 0), "fr") == "Il est midi pile." and r.time_sentence(day(13, 0), "fr") == "Il est 13 heures pile.")
check("weather (fr): no place set", r.weather_sentence({"available": False, "reason": "no_place"}) == "Je ne sais pas où je suis : ma ville n'est pas réglée.")
check("weather (fr): no rain said under 30 %", r.weather_sentence(
    {"available": True, "temperature": -2.4, "today": {"icon": "snow", "min": -5, "max": 1, "rain": 10}})
    == "Il fait -2 degrés. Aujourd'hui : de la neige, entre -5 et 1 degrés.")
check("weather (fr): without the forecast of the day, the temperature only", r.weather_sentence(
    {"available": True, "temperature": 20, "place": "Vichy", "today": None}) == "Il fait 20 degrés à Vichy.")
check("weather: broken answer -> unknown", r.weather_sentence(None) == "Je ne connais pas la météo pour le moment."
      and r.weather_sentence({"available": True}) == "Je ne connais pas la météo pour le moment.")


# What is left of the day, hour by hour (ROADMAP 2.22): today 8 to 18 degrees,
# rain from 16 h, clear at night; tomorrow sunny
def hours_of(temperatures, icons, rains, night_icon="clear"):
    return [{"hour": h, "temperature": temperatures(h), "icon": icons(h) if 6 <= h <= 20 else night_icon,
             "isDay": 7 <= h <= 19, "rain": rains(h)} for h in range(24)]


TODAY = {"date": "2026-10-19", "icon": "rain", "min": 8, "max": 18, "rain": 70,
         "hours": hours_of(lambda h: 8 + min(h, 24 - h) * 10 / 12, lambda h: "rain" if 16 <= h <= 19 else "partly",
                           lambda h: 70 if 16 <= h <= 19 else 0)}
TOMORROW = {"date": "2026-10-20", "icon": "clear", "min": 6, "max": 19, "rain": 0,
            "hours": hours_of(lambda h: 6 + h / 2, lambda h: "clear", lambda h: 0)}


def at(hour, days=(TODAY, TOMORROW)):
    return {"available": True, "temperature": 12, "place": "Madrid", "today": {k: TODAY[k] for k in ("icon", "min", "max", "rain")},
            "now": f"2026-10-19T{hour:02d}", "days": list(days)}


morning = r.weather_sentence(at(9))
check("9 h: the rest of the day (10 h to 21 h; rain for 4 hours: said), the hour of the first rain, not the morning gone",
      morning == "Il fait 12 degrés à Madrid. Pour le reste de la journée : de la pluie, entre 10 et 18 degrés. "
      "Risque de pluie vers 16 heures : 70 pour cent.", morning)
afternoon = r.weather_sentence(at(17))
check("17 h: until this evening, rain now (it lasts: the sky said is rain)",
      afternoon == "Il fait 12 degrés à Madrid. D'ici ce soir : de la pluie, entre 10 et 13 degrés. Risque de pluie vers 18 heures : 70 pour cent.",
      afternoon)
evening = r.weather_sentence(at(20))
check("20 h: tonight (until 5 h tomorrow, \"ciel dégagé\", never \"grand soleil\" at night) and tomorrow",
      evening == "Il fait 12 degrés à Madrid. Cette nuit : ciel dégagé, entre 6 et 10 degrés. Demain : grand soleil, entre 6 et 19 degrés.",
      evening)
check("23 h: tonight from the hours of tomorrow, then tomorrow", r.weather_sentence(at(23)).startswith(
      "Il fait 12 degrés à Madrid. Cette nuit : ciel dégagé, entre 6 et 8 degrés. Demain"), r.weather_sentence(at(23)))
night = r.weather_sentence(at(2))
check("2 h: the rest of the night, then the day to come", night ==
      "Il fait 12 degrés à Madrid. Cette nuit : ciel dégagé, entre 10 et 12 degrés. Dans la journée : de la pluie, entre 10 et 18 degrés. "
      "Risque de pluie vers 16 heures : 70 pour cent.", night)
check("the hour of the place given by the server, not the clock of the Raspberry",
      r.weather_sentence(at(9), now=day(20, 0)) == morning)
no_now = dict(at(9))
del no_now["now"]
check("... else the clock of the Raspberry", r.weather_sentence(no_now, now=day(9, 30)) == morning)
check("one temperature only: \"14 degrés\"", r.weather_sentence(at(9, [dict(TODAY, hours=[
      {"hour": 10, "temperature": 14, "icon": "cloudy", "rain": 0}, {"hour": 11, "temperature": 14.2, "icon": "cloudy", "rain": 0}])]))
      == "Il fait 12 degrés à Madrid. Pour le reste de la journée : ciel couvert, 14 degrés.")
check("broken hours: the forecast of the whole day (as before)", r.weather_sentence(at(9, [{"hours": "x"}]))
      == "Il fait 12 degrés à Madrid. Aujourd'hui : de la pluie, entre 8 et 18 degrés. Risque de pluie : 70 pour cent.")
check("a single storm hour is enough to say storms (the worst sky)", r.sky_of(
      [{"icon": "clear"}, {"icon": "clear"}, {"icon": "storm"}, {"icon": "storm"}]) == "des orages"
      and r.sky_of([{"icon": "partly"}, {"icon": "partly"}, {"icon": "rain"}]) == "quelques nuages")
cfg.LANGUAGE = "en"
check("weather (en): until this evening, around 6 PM", r.weather_sentence(at(17)) ==
      "It is 12 degrees in Madrid. Until this evening: rain, between 10 and 13 degrees. Chance of rain around 6 PM: 70 percent.",
      r.weather_sentence(at(17)))
check("weather (en): tonight, clear skies, tomorrow", r.weather_sentence(at(20)) ==
      "It is 12 degrees in Madrid. Tonight: clear skies, between 6 and 10 degrees. Tomorrow: sunny, between 6 and 19 degrees.", r.weather_sentence(at(20)))
cfg.LANGUAGE = "es"
check("weather (es): resto del día, hacia las 16", r.weather_sentence(at(9)) ==
      "Hace 12 grados en Madrid. Para el resto del día: lluvia, entre 10 y 18 grados. Probabilidad de lluvia hacia las 16: 70 por ciento.",
      r.weather_sentence(at(9)))
cfg.LANGUAGE = "fr"
# "Robot, comment ça va ?": the health report said
for words_heard, wanted in ((("robot", "comment", "ça", "va"), "health"), (("ça", "va", "robot"), "health"),
                            (("robot", "tu", "vas", "bien"), "health"), (("ça", "va"), None)):
    check(f"{' '.join(words_heard)}: {wanted}", v.command_of(result(*words_heard), "fr") == wanted)
check("\"how are you\" / \"cómo estás\"", v.command_of(result("robot", "how", "are", "you"), "en") == "health"
      and v.command_of(result("robot", "cómo", "estás"), "es") == "health")
report = {"checks": [
    {"id": "version", "status": "info", "value": "v0.2.6"},
    {"id": "system.uptime", "status": "info", "value": "3d 04:10"},
    {"id": "mouse", "status": "ok", "value": "HS6209"},
    {"id": "disk", "status": "ok", "value": "43.1 / 52.3 GB (82%)"},
    {"id": "memory", "status": "ok", "value": "926 / 1847 MB (50%)"},
    {"id": "temperature", "status": "ok", "value": "67.2 °C"}]}
check("health, all good: points checked (info ones not counted) and figures",
      r.health_sentence(report) == "Je vais très bien ! J'ai vérifié 4 points, tout fonctionne. Température : 67 degrés. "
      "Mémoire libre : 50 pour cent. Disque libre : 82 pour cent. Allumé depuis 3 jours.", r.health_sentence(report))
report["checks"] += [{"id": "power", "status": "warn", "value": "0x50000"}, {"id": "network.powersave", "status": "warn", "value": "on"}]
check("health, things to check: named", r.health_sentence(report).startswith(
    "Je vais bien. J'ai vérifié 6 points, à surveiller : l'alimentation et l'économie d'énergie du Wi-Fi."), r.health_sentence(report))
report["checks"] += [{"id": "cec", "status": "fail", "value": "no answer"}, {"id": "camera", "status": "fail", "value": "-"},
                     {"id": "speaker", "status": "fail", "value": "HDMI"}]
check("health, failures first, then what to check", r.health_sentence(report).startswith(
    "Ça ne va pas très fort. J'ai vérifié 9 points, en panne : la commande de la télé par HDMI, la caméra et le haut-parleur. "
    "À surveiller : l'alimentation et l'économie d'énergie du Wi-Fi."), r.health_sentence(report))
check("health, not connected to the server: said first",
      "en panne : la connexion au serveur" in r.health_sentence({"checks": []}, connected=False))
check("health, unknown check: its label of the report", "Nouveau test" not in r.check_name("disk") and r.check_name("xyz") == "diag.check.xyz")
check("health, broken report: no crash", r.health_sentence(None).startswith("Je vais très bien")
      and r.health_sentence({"checks": ["x", {"id": "memory", "status": "ok", "value": None}]}).startswith("Je vais très bien"))
check("health: every check of the report has a spoken name (fr, en, es)", all(
    __import__("i18n").MESSAGES[lang].get("voice.health." + c) for lang in ("fr", "en", "es")
    for c in ("update", "system.watchdog", "service.tvControl", "service.chromium", "selfheal", "version.chromium",
              "network.server", "network.interfaces", "network.wifi", "network.powersave", "hdmi", "screen", "cec",
              "weather", "voice", "camera", "microphone", "speaker", "callAudio", "mouse", "disk", "memory",
              "temperature", "power")))
cfg.LANGUAGE = "en"
check("health (en)", r.health_sentence({"checks": [{"id": "camera", "status": "fail"}]})
      == "I am not so well. I checked 1 points, not working: the camera." or
      r.health_sentence({"checks": [{"id": "camera", "status": "fail"}]}).startswith("I am not so well."))
check("time (en): 2:35 PM, o'clock", r.time_sentence(day(14, 35), "en") == "It is 2:35 PM." and r.time_sentence(day(0, 0), "en") == "It is 12 o'clock AM.")
check("weather (en)", r.weather_sentence({"available": True, "temperature": 9, "place": "Leeds", "today": {"icon": "cloudy", "min": 6, "max": 11, "rain": 40}})
      == "It is 9 degrees in Leeds. Today: overcast, between 6 and 11 degrees. Chance of rain: 40 percent.")
cfg.LANGUAGE = "es"
check("time (es): la una, en punto", r.time_sentence(day(13, 10), "es") == "Es la una y 10." and r.time_sentence(day(20, 0), "es") == "Son las 8 en punto.")
check("weather (es)", r.weather_sentence({"available": True, "temperature": 30, "place": "Sevilla", "today": {"icon": "clear", "min": 18, "max": 33, "rain": 0}})
      == "Hace 30 grados en Sevilla. Hoy: sol, entre 18 y 33 grados.")
cfg.LANGUAGE = "fr"


# --- Sentence of the robot ---
calls = []


class FakeGTTS:
    def __init__(self, text, lang):
        calls.append(("gtts", text, lang))

    def save(self, path):
        Path(path).write_bytes(b"mp3")


def fake_run(command, **kwargs):
    calls.append(tuple(command[:2]))
    if command[0] == "ffmpeg":
        Path(command[-1]).write_bytes(b"wav")
    return types.SimpleNamespace(returncode=0)


tts_audio = __import__("importlib").reload(sys.modules["tts_audio"])
tts_audio.gTTS = FakeGTTS
tts_audio.subprocess.run = fake_run
tts_audio.find_ringing_card = lambda: {"id": "AUDIO", "name": "USB"}
tts_audio.set_max_volume = lambda card: None
check("say: sentence generated in the language of the Raspberry and played on the speaker",
      tts_audio.say("voice.hello") is True and ("gtts", "Bonjour, je suis Robot ! Comment je peux t'aider ?", "fr") in calls
      and ("aplay", "-q") in calls, calls)
check("... at the volume said by voice (scale of the ear), not forced to 100 %", ("amixer", "-M") in calls, calls)
mixed = []
tts_audio.set_card_volume = lambda card, percent, mapped=False: mixed.append(percent)
tts_audio.save_radio_volume(20)
tts_audio.play_wav("x.wav")
check("voice of the robot at its own volume (8 = 80 %), not the one of the radio (20 %)", mixed == [80], mixed)
calls.clear()
tts_audio.say("voice.hello")
check("said again: from the cache (no new generation)", not any(c[0] == "gtts" for c in calls) and ("aplay", "-q") in calls)
check("sentence of the robot translated (fr, en, es)", all(
    __import__("i18n").MESSAGES[lang].get("voice.hello") for lang in ("fr", "en", "es")))

real_config = (Path(__file__).resolve().parents[1] / "config.py").read_text(encoding="utf-8")
check("config.py: VOICE_COMMANDS = True by default", "\nVOICE_COMMANDS = True\n" in real_config)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
