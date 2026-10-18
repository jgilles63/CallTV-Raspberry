# Radio, volume and call asked by voice to the robot (radio.py, tts_audio.py,
# voice_commands.py, agent.py; ROADMAP 2.13 level 2). Nothing is played:
# ffmpeg, aplay and amixer are simulated. Checks: stations of config.py
# (invalid ones skipped), last station kept, ffmpeg -> aplay on the USB
# speaker (only http / https streams), paused while the robot speaks, turned
# down while it listens, stream ended by itself; volume 1 to 10 kept, on the
# scale of the ear, ringtone always at 100 %; phrases with a frequency, a
# level or a contact name; agent: radio / stop / volume / call answered,
# radio stopped by a call and by the button, TV contacts from the server,
# refusal of the call said.
import asyncio
import json
import sys
import tempfile
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Raspberry_receiver/

cfg = types.ModuleType("config")
cfg.LANGUAGE = "fr"; cfg.RASPBERRY_ID = "rpi-radio"; cfg.DEVICE_SECRET = "secret"
cfg.SERVER_URL = "wss://x"; cfg.UNAUTHORIZED_RETRY_DELAY = 30; cfg.CALL_DURATION = 30
cfg.MOUSE_DEVICE = None; cfg.MOUSE_RETRY_DELAY = 5; cfg.BASE_DIR = Path(tempfile.mkdtemp())
cfg.CACHE_DIR = Path(tempfile.mkdtemp()); cfg.VOICE_VOLUME = 1.5; cfg.AUDIO_DEVICE = None
cfg.MAX_CALLER_NAME_LENGTH = 30; cfg.MAX_CACHED_CALLS = 5; cfg.RINGTONE_PATH = "x.wav"; cfg.RINGTONE_VOLUME = 0.2
cfg.RADIO_STATIONS = [
    {"name": "France Inter", "frequency": 87.8, "url": "https://icecast.example/franceinter.mp3"},
    {"name": "Radio Test", "frequency": "101.2", "url": "http://stream.example/test"},
    {"name": "Same frequency", "frequency": 101.2, "url": "https://stream.example/other"},
    {"name": "Not FM", "frequency": 150, "url": "https://stream.example/x"},
    {"name": "Local file", "frequency": 95.0, "url": "file:///etc/passwd"},
    {"name": "", "frequency": 96.0, "url": "https://stream.example/noname"},
    "not a station",
]
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

import tts_audio  # noqa: E402
import radio  # noqa: E402
import voice_commands as v  # noqa: E402
import agent  # noqa: E402

passed = failed = 0


def check(label, condition, detail=""):
    global passed, failed
    passed, failed = passed + bool(condition), failed + (not condition)
    print(f"{'OK ' if condition else 'KO '} {label} {detail}")


# --- Stations of config.py ---
found = radio.stations()
check("valid stations only (FM frequency, http / https stream, a name, one per frequency)",
      [s["name"] for s in found] == ["France Inter", "Radio Test"], found)
check("frequency written with one decimal", [s["frequency"] for s in found] == ["87.8", "101.2"])
check("station of a frequency", radio.find("101.2")["name"] == "Radio Test" and radio.find(101.2)["name"] == "Radio Test"
      and radio.find("99.9") is None and radio.find("abc") is None)
check("\"mets la radio\" the first time: the first station", radio.default_station()["name"] == "France Inter")

# --- Volume (1 to 10) ---
amixer = []
tts_audio.subprocess.run = lambda command, **kw: amixer.append(command) or types.SimpleNamespace(returncode=0)
tts_audio.find_ringing_card = lambda: {"id": "AUDIO", "name": "USB"}
check("volume never set: 10 (100 %)", tts_audio.volume_level() == 10)
check("volume 4 kept", tts_audio.save_volume_level(4) and tts_audio.volume_level() == 4)
check("volume 0, 11, text: refused", not tts_audio.save_volume_level(0) and not tts_audio.save_volume_level(11)
      and not tts_audio.save_volume_level("5") and tts_audio.volume_level() == 4)
(cfg.BASE_DIR / tts_audio.VOLUME_FILE_NAME).write_text("99")
check("broken volume file: 10", tts_audio.volume_level() == 10)
tts_audio.save_volume_level(4)
tts_audio.set_speaker_volume()
check("speaker at 40 % on the scale of the ear (amixer -M)", amixer[-1] == ["amixer", "-M", "-c", "AUDIO", "sset", "PCM", "40%"], amixer[-1])
tts_audio.set_speaker_volume(1)
check("turned down while the robot listens: level 1 (10 %)", amixer[-1][-1] == "10%", amixer[-1])
tts_audio.set_max_volume({"id": "AUDIO"})
check("ringtone: always 100 % (not the voice level)", amixer[-1] == ["amixer", "-c", "AUDIO", "sset", "PCM", "100%"], amixer[-1])


# --- Radio played: ffmpeg -> aplay ---
class FakeProcess:
    def __init__(self, command, **kwargs):
        self.command, self.kwargs = command, kwargs
        self.stdout = types.SimpleNamespace(close=lambda: None) if kwargs.get("stdout") == radio.subprocess.PIPE else None
        self.ended = None
        self.terminated = False
        started.append(self)

    def poll(self):
        return self.ended

    def terminate(self):
        self.terminated, self.ended = True, -15

    def wait(self, timeout=None):
        return self.ended

    def kill(self):
        self.ended = -9


started = []
player = radio.Radio(popen=FakeProcess)
check("nothing played at first", not player.on and not player.playing)
player.play(radio.find("101.2"))
reader, aplay = started[-2], started[-1]
check("ffmpeg reads the stream of the station", reader.command[0] == "ffmpeg" and "http://stream.example/test" in reader.command)
check("... only http / https streams (no local file)",
      reader.command[reader.command.index("-protocol_whitelist") + 1] == "http,https,tcp,tls,crypto")
check("... and comes back after a short cut of the internet", "-reconnect" in reader.command)
check("aplay plays it on the USB speaker", aplay.command[:4] == ["aplay", "-q", "-D", "plughw:CARD=AUDIO,DEV=0"])
check("at the volume said by voice", amixer[-1][-1] == "40%")
check("playing, last station kept", player.playing and (cfg.BASE_DIR / radio.LAST_STATION_FILE_NAME).read_text().strip() == "101.2")
check("\"mets la radio\" next time: the last station", radio.default_station()["name"] == "Radio Test")
player.duck()
check("robot listening: radio turned down to level 1", amixer[-1][-1] == "10%")
player.unduck()
check("... then back to its volume", amixer[-1][-1] == "40%")
player.pause()
check("robot speaking: radio paused (one sound at a time on the speaker)",
      reader.terminated and aplay.terminated and player.on and not player.playing)
player.resume()
check("... then it goes on", player.playing and len(started) == 4)
player.play(radio.find("87.8"))
check("another station: the first one stopped", started[2].terminated and started[3].terminated and player.station["name"] == "France Inter")
check("stream still running: nothing to do", player.check() is False and player.on)
started[-2].ended = 1
check("stream ended by itself (internet lost): radio off", player.check() is True and not player.on and started[-1].terminated)
player.play(radio.find("87.8"))
player.stop()
check("stop: radio off", not player.on and started[-1].terminated)


def broken_popen(command, **kwargs):
    raise OSError("ffmpeg missing")


broken = radio.Radio(popen=broken_popen)
broken.play(radio.find("87.8"))
check("ffmpeg missing: no crash", broken.processes == [])
broken.stop()

# --- Phrases with a value ---
contacts = [{"deviceId": "rpi-mamie", "name": "Mamie"}, {"deviceId": "rpi-jp", "name": "Jean-Pierre"},
            {"deviceId": "rpi-other", "name": "mamie"}, {"deviceId": "rpi-bad", "name": "?!"}]
table = v.phrase_table("fr", radio.stations(), contacts)


def said(*words):
    return {"result": [{"word": w, "conf": 0.95} for w in words], "text": " ".join(words)}


for words_heard, wanted in (
        (("robot", "mets", "la", "radio"), "radio"),
        (("robot", "radio"), "radio"),
        (("robot", "radio", "cent", "un", "point", "deux"), "radio:101.2"),
        (("robot", "radio", "cent", "un", "deux"), "radio:101.2"),
        (("radio", "quatre-vingt-sept", "virgule", "huit", "robot"), "radio:87.8"),
        (("robot", "radio", "quatre-vingt-dix", "neuf"), "radio"),  # unknown frequency: the usual radio
        (("robot", "stop"), "stop"),
        (("robot", "arrête", "la", "radio"), "stop"),
        (("robot", "volume", "cinq"), "volume:5"),
        (("robot", "volume", "dix"), "volume:10"),
        (("robot", "appelle", "mamie"), "call:rpi-mamie"),
        (("appeler", "jean-pierre", "robot"), "call:rpi-jp"),
        (("robot", "appelle", "[unk]"), None)):
    check(f"{' '.join(words_heard)}: {wanted}", v.command_of(said(*words_heard), "fr", table=table) == wanted)
check("two contacts of the same name: the first one (newest)", table["appelle mamie"] == "call:rpi-mamie")
check("a name without letters: not callable", not any(c.endswith("rpi-bad") for c in table.values()))
check("frequencies said in English and Spanish",
      v.command_of(said("robot", "radio", "one", "oh", "one", "point", "two"), "en", table=v.phrase_table("en", radio.stations())) == "radio:101.2"
      and v.command_of(said("robot", "radio", "ochenta", "y", "siete", "punto", "ocho"), "es",
                       table=v.phrase_table("es", radio.stations())) == "radio:87.8")
check("volume in English and Spanish",
      v.command_of(said("robot", "volume", "seven"), "en", table=v.phrase_table("en")) == "volume:7"
      and v.command_of(said("robot", "volumen", "siete"), "es", table=v.phrase_table("es")) == "volume:7")
check("call in Spanish", v.command_of(said("robot", "llama", "a", "mamie"), "es",
                                       table=v.phrase_table("es", contacts=contacts)) == "call:rpi-mamie")
check("French numbers", [v.number_words(n, "fr")[0] for n in (21, 71, 80, 91, 99, 100, 108)]
      == ["vingt et un", "soixante et onze", "quatre-vingts", "quatre-vingt-onze", "quatre-vingt-dix-neuf", "cent", "cent huit"])
check("while green, the question alone: \"stop\"", v.command_of(said("stop"), "fr", listening=True, table=table) == "stop")

# Stations asked by their name
for words_heard, wanted in (
        (("robot", "mets", "france", "inter"), "radio:87.8"),
        (("robot", "radio", "test"), "radio:101.2"),
        (("robot", "mets", "la", "radio", "france", "inter"), "radio:87.8"),
        (("france", "inter", "robot"), "radio:87.8")):
    check(f"{' '.join(words_heard)}: {wanted}", v.command_of(said(*words_heard), "fr", table=table) == wanted)
check("while green, the name alone: that station", v.command_of(said("radio", "test"), "fr", listening=True, table=table) == "radio:101.2")
check("names with a number said (\"Europe 1\" -> \"europe un\", \"one\", \"uno\")",
      v.name_phrase("Europe 1", "fr") == "europe un" and v.name_phrase("Europe 1", "en") == "europe one"
      and v.name_phrase("Europe 1", "es") == "europe uno" and v.name_phrase("Europe 1") == "europe")
check("names in English and Spanish", v.phrase_table("en", radio.stations())["play france inter"] == "radio:87.8"
      and v.phrase_table("es", radio.stations())["pon france inter"] == "radio:87.8")
check("the fixed commands win over a station name", v.phrase_table("fr", [{"frequency": "99.0", "name": "Stop"}])["stop"] == "stop")


# New contacts: the recognizer is made again with their names, between two sentences
class FakeRecognizer:
    grammars = []

    def __init__(self, model, rate, grammar):
        FakeRecognizer.grammars.append(json.loads(grammar))

    def SetWords(self, on):
        pass

    def AcceptWaveform(self, data):
        return False

    def Reset(self):
        pass


(cfg.BASE_DIR / "vosk-model" / "conf").mkdir(parents=True)
voice = v.VoiceCommands(loader=lambda path: (object(), FakeRecognizer))
voice.set_choices(stations=radio.stations())
voice.start()
check("stations in the grammar from the start", "robot radio cent un point deux" in FakeRecognizer.grammars[-1])
voice.set_choices(contacts=contacts[:1])
voice.feeding = True
voice.frame(b"\0" * 3200, True)
check("contacts given in the middle of a sentence: grammar kept for now", len(FakeRecognizer.grammars) == 1)
voice.feeding = False
voice.frame(b"\0" * 3200, False)
check("... made again between two sentences, with the name", len(FakeRecognizer.grammars) == 2
      and "robot appelle mamie" in FakeRecognizer.grammars[-1] and "robot radio cent un point deux" in FakeRecognizer.grammars[-1])
voice.set_choices(contacts=contacts[:1])
voice.frame(b"\0" * 3200, False)
check("same contacts again: not made again", len(FakeRecognizer.grammars) == 2)


# --- Agent ---
async def agent_behaviour():
    a = agent.TVControlAgent()
    sent, texts, played = [], [], []

    async def capture(data):
        sent.append(data)

    a.send_message = capture
    a.radio = radio.Radio(popen=FakeProcess)
    a.alert_sound = types.SimpleNamespace(play=lambda name=None: None, stop=lambda: None)
    tts_audio.spoken_wav = lambda key: "hello.wav"
    tts_audio.text_wav = lambda text: texts.append(text) or "now.wav"
    tts_audio.wav_seconds = lambda wav: 1.5
    tts_audio.play_wav = lambda wav: played.append((wav, a.radio.playing)) or True
    a.registered = True

    async def command(name):
        a.last_voice_command_at = 0
        await a.on_voice_command(name)
        await a.voice_answer_task

    await a.handle_message({"type": "tv_contacts", "contacts": [
        {"deviceId": "rpi-mamie", "name": "Mamie", "online": True}, {"deviceId": 5, "name": "x"}, {"name": "no id"}]})
    check("TV contacts of the server: kept, names added to the spoken commands",
          a.contacts == [{"deviceId": "rpi-mamie", "name": "Mamie"}] and a.voice.contacts == a.contacts, a.contacts)

    tts_audio.save_volume_level(8)
    await command("radio")
    check("radio turned on: volume 2 (not too loud)", tts_audio.volume_level() == 2 and amixer[-1][-1] == "20%")
    check("\"mets la radio\": the robot says the last station, then the radio plays",
          texts[-1] == "Je mets France Inter." and a.radio.playing and a.radio.station["name"] == "France Inter", texts)
    check("... the TV page shows it (robot with headphones)",
          {"type": "radio_state", "playing": True, "station": "France Inter", "frequency": "87.8"} in sent, sent)
    check("... the robot stops walking (it listens to the radio)", {"type": "sound_activity", "active": False} in sent)
    sent.clear()
    await a.on_sound_activity(True)
    check("radio on: its sound does not make the robot walk", sent == [])

    await a.on_voice_command(v.LISTENING)
    check("\"robot\" heard while the radio plays: green, radio turned down to level 1",
          {"type": "voice_command", "command": "listening"} in sent and amixer[-1][-1] == "10%")
    await a.on_voice_command(v.LISTENING_OFF)
    check("no question: the radio back to its volume (2)", amixer[-1][-1] == "20%")
    await command("radio:101.2")
    check("\"radio 101.2\": said while the radio is paused, then that station",
          texts[-1] == "Je mets Radio Test." and played[-1] == ("now.wav", False) and a.radio.station["name"] == "Radio Test"
          and a.radio.playing)

    await command("volume:7")
    check("\"volume 7\": kept, said, the radio goes on louder",
          tts_audio.volume_level() == 7 and texts[-1] == "Volume 7." and a.radio.playing and amixer[-1][-1] == "70%")
    await command("radio:87.8")
    check("another station while the radio plays: volume kept (7)", tts_audio.volume_level() == 7 and a.radio.station["name"] == "France Inter", (tts_audio.volume_level(), a.radio.station))
    await command("time")
    check("a question while the radio plays: answered, then the radio goes on", texts[-1].startswith("Il est ") and a.radio.playing)
    agent.diagnostics.run_checks = lambda *args: {"checks": [{"id": "mouse", "status": "ok", "value": "m"},
                                                             {"id": "temperature", "status": "ok", "value": "51.0 °C"}]}
    sent.clear()
    await command("health")
    check("\"comment ça va\": the health report said, the robot looks clever meanwhile",
          texts[-1] == "Je vais très bien ! J'ai vérifié 2 points, tout fonctionne. Température : 51 degrés."
          and {"type": "voice_command", "command": "health", "seconds": 1.5} in sent and a.radio.playing, (texts[-1], sent))

    sent.clear()
    said_before = len(texts)
    await command("stop")
    check("\"stop\": radio off, nothing said, the TV page told",
          not a.radio.on and len(texts) == said_before and sent[-1] == {"type": "radio_state", "playing": False}, sent)
    await command("stop")
    check("\"stop\" without radio: nothing", not a.radio.on)

    await command("radio")
    sent.clear()
    await command("call:rpi-mamie")
    check("\"appelle Mamie\": the robot says it, the radio stops, the call starts from this TV",
          texts[-1] == "J'appelle Mamie." and not a.radio.on
          and sent[-1] == {"type": "tv_call_request", "targetDeviceId": "rpi-mamie"}, sent)
    sent.clear()
    await command("call:rpi-unknown")
    check("a device that is not a contact: nothing", not any(m.get("type") == "tv_call_request" for m in sent))
    await a.handle_message({"type": "tv_call_error", "errorCode": "DEVICE_OFFLINE", "message": "Le Raspberry \"rpi-mamie\" est hors ligne."})
    await a.voice_answer_task
    check("call refused by the server (offline): the robot says it with the name of the contact",
          texts[-1] == "La télé de Mamie n'est pas connectée pour le moment.", texts[-1])
    count = len(texts)
    await a.handle_message({"type": "tv_call_error", "errorCode": "DEVICE_OFFLINE"})
    check("a refusal for a call not asked by voice: nothing said", len(texts) == count)
    a.voice_call_name = "Mamie"
    await a.handle_message({"type": "tv_call_error", "errorCode": "RATE_LIMITED"})
    await a.voice_answer_task
    check("other refusal: \"I cannot call Mamie right now\"", texts[-1] == "Je n'arrive pas à appeler Mamie pour le moment.")

    await command("radio")
    await a.handle_message({"type": "incoming_call", "callId": "c-1", "callerName": "Paul"})
    check("a call arrives: radio stopped", not a.radio.on)
    a.call_window, a.current_call_id = False, None
    await command("radio")
    await a.on_mouse_click_async()
    check("the button outside a call: radio stopped", not a.radio.on)
    await command("radio")
    sent.clear()
    await a.handle_message({"type": "radio_stop"})
    check("\"Stop\" button of the TV page: radio stopped, the page told",
          not a.radio.on and sent == [{"type": "radio_state", "playing": False}], sent)

    sent.clear()
    await a.handle_message({"type": "register_ack", "status": "ok"})
    check("connected: TV contacts asked, radio state sent",
          {"type": "tv_contacts_request"} in sent and {"type": "radio_state", "playing": False} in sent, sent)

    a.active_call_id = "c-2"
    sent.clear()
    await a.on_voice_command("radio")
    check("during a call: nothing", sent == [] and not a.radio.on)
    a.active_call_id = None


asyncio.run(agent_behaviour())

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
