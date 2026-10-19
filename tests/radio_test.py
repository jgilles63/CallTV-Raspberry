# Radio, volume and call asked by voice to the robot (radio.py, tts_audio.py,
# voice_commands.py, agent.py; ROADMAP 2.13 level 2). Nothing is played:
# ffmpeg, aplay and amixer are simulated. Checks: stations of config.py
# (invalid ones skipped), last station kept, ffmpeg -> aplay on the USB
# speaker (only http / https streams), paused while the robot speaks, turned
# down while it listens, stream ended by itself; volume 1 to 10 kept, on the
# scale of the ear, ringtone always at 100 %; phrases with a frequency, a
# level or a contact name; agent: radio / stop / volume / call answered,
# radio stopped by a call and by the button, TV contacts from the server,
# refusal of the call said. Radio page of the TV (ROADMAP 2.18): level of the
# sound measured between ffmpeg and aplay, station played from the page,
# levels sent while the page is open.
import array
import asyncio
import io
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
# Stations sent to the TV page with the state of the radio
STATIONS = [{"name": "France Inter", "frequency": "87.8"}, {"name": "Radio Test", "frequency": "101.2"}]


def radio_state(playing, **station):
    return {"type": "radio_state", "playing": playing, "volume": tts_audio.radio_volume(), "stations": STATIONS, **station}


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

# --- Stations of the country of the TV (radio_stations.py, ROADMAP 2.21) ---
import radio_stations as rs  # noqa: E402
check("country names: fr / en / es / pt, accents and case ignored",
      [rs.country_code(c) for c in ("Espagne", "ESPAÑA", " spain ", "es", "États-Unis", "USA", "Estados Unidos", "Royaume-Uni",
                                    "Angleterre", "England", "uk", "Mexique", "México", "Portugal", "France", "Francia")]
      == ["ES", "ES", "ES", "ES", "US", "US", "US", "GB", "GB", "GB", "GB", "MX", "MX", "PT", "FR", "FR"])
check("unknown country: none", rs.country_code("Italie") is None and rs.country_code(None) is None and rs.country_code("") is None)
check("unknown country: the stations of the language (es -> Spain, en -> United Kingdom), else France",
      rs.stations_for("Italie", "es")[0]["name"] == "Radio Nacional" and rs.stations_for(None, "en")[0]["name"] == "BBC Radio 1"
      and rs.stations_for(None, None)[0]["name"] == "France Inter")
for code, country_stations in rs.STATIONS.items():
    frequencies = [radio.frequency_text(s["frequency"]) for s in country_stations]
    check(f"{code}: 10 to 12 stations, a name, an FM frequency each (all different), an http(s) stream",
          10 <= len(country_stations) <= 12 and all(s["name"] for s in country_stations) and None not in frequencies
          and len(set(frequencies)) == len(frequencies)
          and all(s["url"].startswith(("https://", "http://")) and " " not in s["url"] for s in country_stations), code)
own_stations, cfg.RADIO_STATIONS = cfg.RADIO_STATIONS, None
cfg.WEATHER_COUNTRY = "Espagne"
check("no list of one's own (None): the stations of the country of the settings page",
      [s["name"] for s in radio.stations()][:4] == ["Radio Nacional", "Radio Clásica", "Radio 3", "Cadena SER"]
      and radio.find("105.4")["name"] == "Cadena SER")
check("... their names said to the robot in Spanish (\"Robot, pon Cadena SER\", \"Robot, Los 40\")",
      v.phrase_table("es", radio.stations())["pon cadena ser"] == "radio:105.4"
      and v.phrase_table("es", radio.stations())["los cuarenta"] == "radio:93.9")
rs.STATIONS["ES"][0]["name"] = "changed"
check("the lists of the module are never changed by the radio", rs.STATIONS["ES"][0]["name"] == "changed"
      and radio.stations()[0]["name"] == "changed")
rs.STATIONS["ES"][0]["name"] = "Radio Nacional"
cfg.WEATHER_COUNTRY = "Mexique"
check("Mexique: the stations of Mexico City", radio.stations()[0]["name"] == "W Radio")
cfg.RADIO_STATIONS, cfg.WEATHER_COUNTRY = own_stations, None
check("a list of one's own in config.py wins over the country", radio.stations()[0]["name"] == "France Inter")

# --- Volume (1 to 10) ---
amixer = []
tts_audio.subprocess.run = lambda command, **kw: amixer.append(command) or types.SimpleNamespace(returncode=0)
tts_audio.find_ringing_card = lambda: {"id": "AUDIO", "name": "USB"}
check("radio volume never set: 20 %", tts_audio.radio_volume() == 20)
(cfg.BASE_DIR / tts_audio.OLD_VOLUME_FILE_NAME).write_text("3\n")
check("old volume file of the radio (level 3, before 19/10/2026): 30 %", tts_audio.radio_volume() == 30)
check("radio volume 37 % kept (slider of the radio page)", tts_audio.save_radio_volume(37) and tts_audio.radio_volume() == 37)
check("0 % allowed (silent); 101, -1, text, True: refused", tts_audio.save_radio_volume(0) and tts_audio.radio_volume() == 0
      and not tts_audio.save_radio_volume(101) and not tts_audio.save_radio_volume(-1) and not tts_audio.save_radio_volume("5")
      and not tts_audio.save_radio_volume(True) and tts_audio.radio_volume() == 0)
(cfg.BASE_DIR / tts_audio.RADIO_VOLUME_FILE_NAME).write_text("999")
check("broken radio volume file: the old file (30 %)", tts_audio.radio_volume() == 30)
check("voice of the robot never set: 8 (not the volume of the radio)", tts_audio.voice_level() == 8)
check("voice of the robot kept apart", tts_audio.save_voice_level(6) and tts_audio.voice_level() == 6
      and tts_audio.radio_volume() == 30 and not tts_audio.save_voice_level(0) and tts_audio.voice_level() == 6)
tts_audio.save_voice_level(8)
tts_audio.save_radio_volume(40)
tts_audio.set_speaker_volume()
check("speaker at 40 % on the scale of the ear (amixer -M)", amixer[-1] == ["amixer", "-M", "-c", "AUDIO", "sset", "PCM", "40%"], amixer[-1])
tts_audio.set_speaker_volume(10)
check("turned down while the robot listens: 10 %", amixer[-1][-1] == "10%", amixer[-1])
tts_audio.set_max_volume({"id": "AUDIO"})
check("ringtone: always 100 % (not the voice level)", amixer[-1] == ["amixer", "-c", "AUDIO", "sset", "PCM", "100%"], amixer[-1])


# --- Radio played: ffmpeg -> aplay ---
class FakeProcess:
    def __init__(self, command, **kwargs):
        self.command, self.kwargs = command, kwargs
        self.stdout = types.SimpleNamespace(close=lambda: None) if kwargs.get("stdout") == radio.subprocess.PIPE else None
        self.stdin = None
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
check("... the sound goes through the agent (level of the sound measured on the way)",
      reader.kwargs["stdout"] == radio.subprocess.PIPE and aplay.kwargs["stdin"] == radio.subprocess.PIPE)
check("at the volume said by voice", amixer[-1][-1] == "40%")
check("playing, last station kept", player.playing and (cfg.BASE_DIR / radio.LAST_STATION_FILE_NAME).read_text().strip() == "101.2")
check("\"mets la radio\" next time: the last station", radio.default_station()["name"] == "Radio Test")
player.duck()
check("robot listening: radio turned down to 10 %", amixer[-1][-1] == "10%")
tts_audio.save_radio_volume(5)
player.duck()
check("... never louder than the radio itself (5 %)", amixer[-1][-1] == "5%")
tts_audio.save_radio_volume(40)
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


# --- Level of the sound (wave of the radio page) ---
def tone(peak, frames=radio.CHUNK_BYTES // 4):
    return array.array("h", [peak, -peak] * frames).tobytes()


check("level: silence 0, full sound 100, half sound (-6 dB) 88",
      radio.level_of(tone(0)) == 0 and radio.level_of(tone(32767)) == 100 and radio.level_of(tone(16384)) == 88,
      (radio.level_of(tone(16384)),))
check("level: very quiet (under -50 dB) 0, odd or empty piece: no crash",
      radio.level_of(tone(50)) == 0 and radio.level_of(b"\x01") == 0 and radio.level_of(tone(32767)[:-1]) == 100)


class Sink(io.BytesIO):
    def close(self):
        self.closed_by_pump = True


source, sink = io.BytesIO(tone(0) + tone(32767) + tone(16384)[:100]), Sink()
pumped = radio.Radio(popen=FakeProcess)
pumped.pump(source, sink)
check("ffmpeg -> aplay: the whole sound passed on, one level per 50 ms piece",
      sink.getvalue() == tone(0) + tone(32767) + tone(16384)[:100] and pumped.levels() == [0, 100, 88]
      and sink.closed_by_pump, pumped.levels())
check("levels taken: none left until new sound", pumped.levels() == [])


class DeadSink(Sink):
    def write(self, data):
        raise BrokenPipeError("aplay stopped")


pumped.pump(io.BytesIO(tone(100) * 3), DeadSink())
check("aplay stopped (pause, stop): the pump ends without a crash", len(pumped.levels()) == 1)
for _ in range(radio.MAX_LEVELS + 5):
    pumped.sound_levels.append(1)
check("levels never taken (page closed): the last MAX_LEVELS only", len(pumped.levels()) == radio.MAX_LEVELS)


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

    tts_audio.save_radio_volume(20)
    await command("radio")
    check("radio turned on: at its volume (20 %)", tts_audio.radio_volume() == 20 and amixer[-1][-1] == "20%")
    check("... the voice of the robot stays loud (8)", tts_audio.voice_level() == 8)
    check("\"mets la radio\": the robot says the last station, then the radio plays",
          texts[-1] == "Je mets France Inter." and a.radio.playing and a.radio.station["name"] == "France Inter", texts)
    check("... the TV page shows it (robot with headphones)",
          radio_state(True, station="France Inter", frequency="87.8") in sent, sent)
    check("... the robot stops walking (it listens to the radio)", {"type": "sound_activity", "active": False} in sent)
    sent.clear()
    await a.on_sound_activity(True)
    check("radio on: its sound does not make the robot walk", sent == [])

    await a.on_voice_command(v.LISTENING)
    check("\"robot\" heard while the radio plays: green, radio turned down to 10 %",
          {"type": "voice_command", "command": "listening"} in sent and amixer[-1][-1] == "10%")
    await a.on_voice_command(v.LISTENING_OFF)
    check("no question: the radio back to its volume (2)", amixer[-1][-1] == "20%")
    await command("radio:101.2")
    check("\"radio 101.2\": said while the radio is paused, then that station",
          texts[-1] == "Je mets Radio Test." and played[-1] == ("now.wav", False) and a.radio.station["name"] == "Radio Test"
          and a.radio.playing)

    voice_before = tts_audio.voice_level()
    sent.clear()
    await command("volume:7")
    check("\"volume 7\" while the radio plays: the radio at 70 %, the voice of the robot unchanged",
          tts_audio.radio_volume() == 70 and texts[-1] == "Volume 7." and a.radio.playing and amixer[-1][-1] == "70%"
          and tts_audio.voice_level() == voice_before)
    check("... the slider of the radio page follows (radio_state with the volume)",
          any(m.get("type") == "radio_state" and m.get("volume") == 70 for m in sent), sent)
    await command("radio:87.8")
    check("another station while the radio plays: volume kept (70 %)", tts_audio.radio_volume() == 70 and a.radio.station["name"] == "France Inter")
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
          not a.radio.on and len(texts) == said_before and sent[-1] == radio_state(False), sent)
    await command("stop")
    check("\"stop\" without radio: nothing", not a.radio.on)
    radio_before = tts_audio.radio_volume()
    await command("volume:9")
    check("\"volume 9\" without radio: the voice of the robot (said at once at 9), the radio unchanged",
          tts_audio.voice_level() == 9 and tts_audio.radio_volume() == radio_before and texts[-1] == "Volume 9.")
    tts_audio.save_voice_level(8)

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
          not a.radio.on and sent == [radio_state(False)], sent)

    sent.clear()
    await a.handle_message({"type": "register_ack", "status": "ok"})
    check("connected: TV contacts asked, radio state sent",
          {"type": "tv_contacts_request"} in sent and radio_state(False) in sent, sent)

    a.active_call_id = "c-2"
    sent.clear()
    await a.on_voice_command("radio")
    check("during a call: nothing", sent == [] and not a.radio.on)
    await a.handle_message({"type": "radio_play", "frequency": "87.8"})
    check("during a call: no radio from the page either", not a.radio.on and sent == [radio_state(False)], sent)
    a.active_call_id = None

    # --- Radio page of the TV ---
    sent.clear()
    await a.handle_message({"type": "radio_request"})
    check("radio page opened: the stations and the state", sent == [radio_state(False)], sent)
    sent.clear()
    said_before = len(texts)
    tts_audio.save_radio_volume(60)
    await a.handle_message({"type": "radio_play", "frequency": "101.2"})
    check("Play on the page: the station plays at once, nothing said, at the volume of the radio (60 %)",
          a.radio.playing and a.radio.station["name"] == "Radio Test" and len(texts) == said_before
          and amixer[-1][-1] == "60%" and sent[-1] == radio_state(True, station="Radio Test", frequency="101.2"), sent)
    tts_audio.save_radio_volume(50)
    first = started[-1]
    await a.handle_message({"type": "radio_play", "frequency": "101.2"})
    check("the same station again: not started again", started[-1] is first and a.radio.playing)
    await a.handle_message({"type": "radio_play", "frequency": "87.8"})
    check("another station from the tuner: played, volume kept (50 %)",
          a.radio.station["name"] == "France Inter" and tts_audio.radio_volume() == 50)
    await a.handle_message({"type": "radio_volume", "percent": 35})
    check("slider of the radio page: kept and heard at once", tts_audio.radio_volume() == 35 and amixer[-1][-1] == "35%")
    count = len(amixer)
    for bad in (101, -5, "50", None, 12.5, True):
        await a.handle_message({"type": "radio_volume", "percent": bad})
    check("strange volumes: nothing changes", tts_audio.radio_volume() == 35 and len(amixer) == count)
    a.radio.stop()
    await a.handle_message({"type": "radio_volume", "percent": 45})
    check("radio off: the volume kept for later, the speaker not touched", tts_audio.radio_volume() == 45 and len(amixer) == count)
    await a.handle_message({"type": "radio_play", "frequency": "87.8"})
    sent.clear()
    for bad in ("99.9", 87.8, None, "<b>"):
        await a.handle_message({"type": "radio_play", "frequency": bad})
    check("unknown or bad frequency: nothing changes, the state is sent again",
          a.radio.station["name"] == "France Inter" and sent == [radio_state(True, station="France Inter", frequency="87.8")] * 4)

    sent.clear()
    agent.RADIO_LEVEL_EVERY = 0.01
    a.radio.levels()
    await a.handle_message({"type": "radio_watch", "on": True})
    task = a.radio_level_task
    a.radio.sound_levels.extend([10, 60, 90])
    await asyncio.sleep(0.05)
    check("page open (radio_watch): the levels of the sound sent", {"type": "radio_level", "levels": [10, 60, 90]} in sent, sent)
    await a.handle_message({"type": "radio_watch", "on": True})
    check("asked again (every minute): still one sender", a.radio_level_task is task)
    await a.stop_radio()
    sent.clear()
    a.radio.sound_levels.extend([50])
    await asyncio.sleep(0.05)
    check("radio stopped: no levels sent", not any(m["type"] == "radio_level" for m in sent))
    await a.handle_message({"type": "radio_watch", "on": False})
    await asyncio.sleep(0.05)
    check("page closed: the sender ends", task.done())
    a.radio_watch_until = 0


asyncio.run(agent_behaviour())

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
