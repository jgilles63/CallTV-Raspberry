# ============================================
# FILE: voice_commands.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spoken commands to the robot of the home screen (ROADMAP 2.13, level 2).

The wake word "robot" says that a command follows, before or after it:
"Robot bonjour" / "Bonjour robot" (the robot waves and answers "Bonjour, je
suis Robot"), "Robot, quelle heure est-il ?" (it says the time), "Robot, quel
temps fait-il ?" (it says the weather of today), "Robot, mets la radio" /
"Robot, radio 101.2" / "Robot ... stop" (radio.py), "Robot, volume 5" (1 to
10), "Robot, appelle Mamie" (a TV contact: the call starts on the TV);
while it rings, "Robot, décroche" / "Robot, raccroche". The
answers are made by the agent (robot_answers.py) and said on the speaker.

A command is one of the phrases exactly (the frequencies of the stations of
config.py and the names of the TV contacts are part of them, set_choices),
with the wake word just before or after it. frame() returns its name, with
its value after ":" for some ("radio:101.2", "volume:5", "call:<device id>").

"Robot" said alone: the robot listens (its eyes and mouth turn green on the
TV, LISTENING) for a few seconds; the question alone is then enough
("quelle heure est-il"), if it is the very next thing said. It goes away
(LISTENING_OFF) when the time is over or when something else is said. Only
a sure "robot" said alone turns it green (high confidence, nothing else in
the result), and only one of the phrases exactly is then taken: with the
few words of the grammar, an ordinary sentence easily gives a "robot" in the
partial results, or a single "heure" / "temps" ("cet après-midi", "en même
temps"; measured on a real Pi on 18/10/2026).

Speech recognition offline with Vosk (small model of the language of the
Raspberry, ~40 MB, installed by install.sh in ~/AppelerMamie/vosk-model):
nothing leaves the Raspberry. The recognizer only knows the words of the
commands (closed grammar): far more reliable and lighter than a free
dictation, and a word heard alone ("robot", "bonjour") does nothing.

The audio comes from sound_level.py (same microphone stream): the
recognizer only works while a sound is heard (plus the half second before
it, so that the start of "robot" is not cut). The model is loaded when the
microphone is listened to and unloaded during the calls (start / stop): the
memory of a call stays the same as without voice commands.
config.VOICE_COMMANDS = False turns it off.
"""

import collections
import gc
import json
import re
import time

import config
from i18n import language

SAMPLE_RATE = 16000
MODEL_DIR_NAME = "vosk-model"
# Wake word, and for each command and language the phrases that the
# recognizer knows (all in the vocabulary of the small Vosk models, checked
# on a real Pi on 18/10/2026)
WAKE_WORDS = {"fr": "robot", "en": "robot", "es": "robot"}
COMMANDS = {
    "hello": {"fr": ["bonjour"], "en": ["hello"], "es": ["hola"]},
    "time": {"fr": ["quelle heure est il", "quelle heure"],
             "en": ["what time is it", "what time"],
             "es": ["qué hora es", "qué hora"]},
    "weather": {"fr": ["quel temps fait il", "quel temps"],
                "en": ["what is the weather", "how is the weather", "the weather"],
                "es": ["qué tiempo hace", "qué tiempo"]},
    "radio": {"fr": ["mets la radio", "allume la radio", "la radio", "radio"],
              "en": ["play the radio", "turn on the radio", "the radio", "radio"],
              "es": ["pon la radio", "enciende la radio", "la radio", "radio"]},
    "health": {"fr": ["comment ça va", "ça va", "comment vas tu", "tu vas bien"],
               "en": ["how are you", "are you ok", "are you okay"],
               "es": ["cómo estás", "qué tal", "estás bien"]},
    # Only while it rings (agent.py): answer or decline the call
    "answer": {"fr": ["décroche", "réponds"], "en": ["answer", "pick up"], "es": ["contesta", "descuelga", "responde"]},
    "decline": {"fr": ["raccroche", "refuse"], "en": ["hang up", "decline"], "es": ["cuelga", "rechaza"]},
    "stop": {"fr": ["stop", "arrête", "arrête la radio", "coupe la radio"],
             "en": ["stop", "stop the radio", "turn off the radio"],
             "es": ["para", "para la radio", "apaga la radio", "stop"]},
}
# Phrases with a value: {} is the frequency, the level or the name
RADIO_PHRASES = {"fr": ["radio {}"], "en": ["radio {}"], "es": ["radio {}"]}
VOLUME_PHRASES = {"fr": ["volume {}"], "en": ["volume {}"], "es": ["volumen {}"]}
CALL_PHRASES = {"fr": ["appelle {}", "appeler {}"], "en": ["call {}"], "es": ["llama a {}", "llamar a {}"]}
# A station asked by its name ("Robot, mets France Inter", "Robot, Nostalgie")
STATION_PHRASES = {"fr": ["mets {}", "mets la radio {}", "radio {}", "{}"], "en": ["play {}", "radio {}", "{}"],
                   "es": ["pon {}", "radio {}", "{}"]}
# Decimal point of a frequency said ("cent un point deux"; also without it)
FREQUENCY_POINTS = {"fr": ["point", "virgule", ""], "en": ["point"], "es": ["punto", "coma", ""]}
# Words of a contact name kept at most
MAX_NAME_WORDS = 4

FR_UNITS = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze",
            "douze", "treize", "quatorze", "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf"]
FR_TENS = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}
EN_UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
            "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
EN_TENS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty", 7: "seventy", 8: "eighty", 9: "ninety"}
ES_UNITS = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once",
            "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte",
            "veintiuno", "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete",
            "veintiocho", "veintinueve"]
ES_TENS = {3: "treinta", 4: "cuarenta", 5: "cincuenta", 6: "sesenta", 7: "setenta", 8: "ochenta", 9: "noventa"}


def number_words(n, lang):
    """Ways to say a number from 0 to 109, as the Vosk models write them."""
    if lang == "en":
        if n < 20:
            return [EN_UNITS[n]]
        if n < 100:
            return [EN_TENS[n // 10] + ("" if n % 10 == 0 else " " + EN_UNITS[n % 10])]
        if n == 100:
            return ["one hundred"]
        return [f"one hundred {EN_UNITS[n - 100]}", f"one hundred and {EN_UNITS[n - 100]}", f"one oh {EN_UNITS[n - 100]}"]
    if lang == "es":
        if n < 30:
            return [ES_UNITS[n]]
        if n < 100:
            return [ES_TENS[n // 10] + ("" if n % 10 == 0 else " y " + ES_UNITS[n % 10])]
        return ["cien"] if n == 100 else [f"ciento {ES_UNITS[n - 100]}"]
    # French
    if n < 20:
        return [FR_UNITS[n]]
    if n < 70:
        tens, unit = divmod(n, 10)
        return [FR_TENS[tens] + ("" if unit == 0 else " et un" if unit == 1 else "-" + FR_UNITS[unit])]
    if n < 80:
        return ["soixante et onze" if n == 71 else "soixante-" + FR_UNITS[n - 60]]
    if n < 100:
        return ["quatre-vingts" if n == 80 else "quatre-vingt-" + FR_UNITS[n - 80]]
    return ["cent"] if n == 100 else [f"cent {FR_UNITS[n - 100]}"]


def frequency_phrases(frequency, lang):
    """Ways to say a frequency ("101.2" -> "cent un point deux", "cent un deux"...)."""
    whole, decimal = (int(part) for part in frequency.split("."))
    phrases = []
    for whole_words in number_words(whole, lang):
        for point in FREQUENCY_POINTS.get(lang, FREQUENCY_POINTS["fr"]):
            for decimal_words in number_words(decimal, lang):
                phrases.append(" ".join(w for w in (whole_words, point, decimal_words) if w))
        if decimal == 0:
            phrases.append(whole_words)
    return phrases


def name_phrase(name, lang=None):
    """
    Name as the recognizer writes it ("Mamie Jeanne" -> "mamie jeanne"), or "".
    lang: the numbers are said ("Europe 1" -> "europe un"), else removed.
    """
    text = str(name or "").lower()
    if lang:
        text = re.sub(r"\d+", lambda m: " " + (number_words(int(m.group()), lang)[0] if int(m.group()) < 110 else "") + " ", text)
    words_of_name = re.sub(r"[^\w\s'-]|_|\d", " ", text).split()
    return " ".join(words_of_name[:MAX_NAME_WORDS])


def enabled():
    return getattr(config, "VOICE_COMMANDS", True) is not False


def model_dir():
    return config.BASE_DIR / MODEL_DIR_NAME


def wake_word(lang):
    return WAKE_WORDS.get(lang, WAKE_WORDS["fr"])


def phrase_table(lang, stations=(), contacts=()):
    """
    {phrase: command} of a language: the fixed commands, the frequencies of
    the stations ([{"frequency": "101.2"}...]), the volume levels, the TV
    contacts ([{"deviceId", "name"}...], the first one of a name wins).
    """
    table = {}

    def add(phrase, command):
        if phrase and phrase not in table:
            table[phrase] = command

    for name, by_lang in COMMANDS.items():
        for phrase in by_lang.get(lang, by_lang["fr"]):
            add(phrase, name)
    for station in stations:
        for said in frequency_phrases(station["frequency"], lang):
            for phrase in RADIO_PHRASES.get(lang, RADIO_PHRASES["fr"]):
                add(phrase.format(said), "radio:" + station["frequency"])
    for station in stations:
        said = name_phrase(station.get("name"), lang)
        if said:
            for phrase in STATION_PHRASES.get(lang, STATION_PHRASES["fr"]):
                add(phrase.format(said), "radio:" + station["frequency"])
    for level in range(1, 11):
        for said in number_words(level, lang):
            for phrase in VOLUME_PHRASES.get(lang, VOLUME_PHRASES["fr"]):
                add(phrase.format(said), f"volume:{level}")
    for contact in contacts:
        said = name_phrase(contact.get("name"))
        if said and contact.get("deviceId"):
            for phrase in CALL_PHRASES.get(lang, CALL_PHRASES["fr"]):
                add(phrase.format(said), "call:" + contact["deviceId"])
    return table


def grammar(lang, table=None):
    """Phrases the recognizer may hear: the commands with the wake word before or after, alone, anything else."""
    wake = wake_word(lang)
    phrases = []
    for phrase in table if table is not None else phrase_table(lang):
        phrases += [f"{wake} {phrase}", f"{phrase} {wake}", phrase]
    # Accents written as they are: Vosk does not read "é" (qué)
    return json.dumps(phrases + [wake, "[unk]"], ensure_ascii=False)


# Each word of a command must be recognized with at least this confidence
# (measured on a real Pi, 18/10/2026: "robot" 0.93 to 1.0, "bonjour" 0.51 to
# 0.58 in a real command; ordinary sentences only gave single words)
MIN_CONFIDENCE = 0.4
# A short pause may split a command into two results: the last words of a
# result still count with the next one for this long
PAIR_SECONDS = 3
CARRIED_WORDS = 5
# Audio kept before a sound is heard, and fed after it ended (frames of 100 ms)
PREROLL_FRAMES = 6
TAIL_FRAMES = 8
# "Robot" alone: the robot listens (green) for this long at most
LISTEN_SECONDS = 6
# "Robot" turns the robot green only with this confidence (a real "robot":
# 0.93 to 1.0 near the microphone; lower from far, in a big room)
WAKE_CONFIDENCE = 0.8
# While it rings, only these commands, read in the partial results: the
# ringtone never stops, so a sentence never "ends" (seen on the TV on
# 18/10/2026: one long result of 12 s, the announcement heard with it)
RINGING_COMMANDS = ("answer", "decline")
# Events returned by frame() besides the commands: the robot listens / no longer
LISTENING = "listening"
LISTENING_OFF = "listening_off"


def heard_words(result):
    """[(word, confidence)] of a result of Vosk ({"result": [{"word", "conf"}...], "text"})."""
    return [(w.get("word"), w.get("conf", 0)) for w in result.get("result", []) if isinstance(w, dict)]


def command_of(result, lang, before=(), listening=False, table=None):
    """
    Command of a result of Vosk, or None: one of the phrases exactly, with
    the wake word just before or after it ("robot quelle heure", "heure est
    il robot"; never "robot [unk] heure"), every word recognized with enough
    confidence. before: words heard just before (end of the previous
    result). listening: "robot" was said just before (the robot is green):
    the phrase alone is enough, if it is the whole result.
    """
    table = phrase_table(lang) if table is None else table
    wake = wake_word(lang)
    heard = heard_words(result)
    if listening:
        if heard and all(conf >= MIN_CONFIDENCE for _w, conf in heard):
            return table.get(" ".join(w for w, _c in heard))
        return None
    sequence = list(before) + heard
    first_new = len(before)
    for i in range(len(sequence)):
        # The longest phrase first ("robot radio cent un deux", not "robot radio")
        for j in range(len(sequence), max(i + 1, first_new), -1):
            window = sequence[i:j]
            if len(window) < 2 or any(conf < MIN_CONFIDENCE for _w, conf in window):
                continue
            said = [w for w, _c in window]
            if said[0] == wake and " ".join(said[1:]) in table:
                return table[" ".join(said[1:])]
            if said[-1] == wake and " ".join(said[:-1]) in table:
                return table[" ".join(said[:-1])]
    return None


def wake_heard(result, lang):
    """
    A sure "robot" said alone in a result of Vosk: high confidence, nothing
    else (an ordinary sentence gives "[unk]", or "robot robot").
    """
    heard = heard_words(result)
    return len(heard) == 1 and heard[0][0] == wake_word(lang) and heard[0][1] >= WAKE_CONFIDENCE


def load_vosk_model(path):
    """Vosk model of a folder (Vosk imported only when used)."""
    import vosk
    vosk.SetLogLevel(-1)
    return vosk.Model(str(path)), vosk.KaldiRecognizer


class VoiceCommands:
    """Recognizer fed with the frames of sound_level.py; frame() returns a command or None."""

    def __init__(self, loader=load_vosk_model):
        self.loader = loader
        self.model = None
        self.recognizer = None
        self.lang = None
        self.preroll = collections.deque(maxlen=PREROLL_FRAMES)
        self.feeding = False
        self.tail = 0
        self.muted_until = 0.0
        self.notice_shown = False
        # Last words heard and when (count with the next result, see PAIR_SECONDS)
        self.last_words = []
        self.last_word_at = 0.0
        # "Robot" said alone: the robot listens until then (0: not listening);
        # green shown on the TV
        self.listening_until = 0.0
        self.green_shown = False
        # Stations and TV contacts said by name (set_choices); the grammar is
        # made again with them at the next frame
        self.stations, self.contacts = [], []
        self.table = None
        self.recognizer_class = None
        self.grammar_changed = False
        # True while it rings (set by the agent): partial results read
        self.is_ringing = lambda: False

    @property
    def listening(self):
        return time.monotonic() < self.listening_until

    def start(self):
        """Loads the model (about 1.5 s on a Raspberry Pi 4); nothing if missing or turned off."""
        if self.recognizer is not None or not enabled():
            return
        path = model_dir()
        if not (path / "conf").is_dir() and not (path / "am").is_dir():
            if not self.notice_shown:
                print(f"ℹ️ No speech recognition model in {path}: no voice commands")
                self.notice_shown = True
            return
        try:
            self.lang = language()
            self.model, self.recognizer_class = self.loader(path)
            self._new_recognizer()
            self.notice_shown = False
            print("🗣️ Voice commands ready")
        except Exception as e:
            self.model = self.recognizer = None
            if not self.notice_shown:
                print(f"⚠️ Voice commands not available ({e})")
                self.notice_shown = True

    def _new_recognizer(self):
        self.table = phrase_table(self.lang, self.stations, self.contacts)
        self.recognizer = self.recognizer_class(self.model, SAMPLE_RATE, grammar(self.lang, self.table))
        self.recognizer.SetWords(True)
        try:
            # Confidence of the words of the partial results too (while it rings)
            self.recognizer.SetPartialWords(True)
        except AttributeError:
            pass
        self.grammar_changed = False

    def set_choices(self, stations=None, contacts=None):
        """
        Stations ([{"frequency"}...]) and TV contacts ([{"deviceId", "name"}...])
        said by voice; the recognizer is made again with them if they changed.
        """
        stations = [s for s in (stations if stations is not None else self.stations)]
        contacts = [c for c in (contacts if contacts is not None else self.contacts)]
        if stations != self.stations or contacts != self.contacts:
            self.stations, self.contacts = stations, contacts
            self.grammar_changed = True

    def stop(self):
        """Unloads the model (a call starts): its memory is given back."""
        if self.recognizer is None and self.model is None:
            return
        self.recognizer = self.model = None
        self.preroll.clear()
        self.feeding = False
        self.listening_until, self.green_shown = 0.0, False
        gc.collect()
        print("🗣️ Voice commands paused (model unloaded)")

    @property
    def ready(self):
        return self.recognizer is not None

    def mute(self, seconds):
        """Nothing is recognized for this long (the robot speaks: it must not hear itself)."""
        self.muted_until = time.monotonic() + seconds
        self.preroll.clear()
        self.last_words = []
        self.listening_until, self.green_shown = 0.0, False
        if self.feeding and self.recognizer is not None:
            self.recognizer.Reset()
        self.feeding = False

    def _command(self, result):
        """
        Command of a result (with the last words of the previous one if
        recent), LISTENING / LISTENING_OFF for the green of the robot, or None.
        """
        now = time.monotonic()
        listening = self.listening
        # While green, the question must be the next thing said, alone
        before = self.last_words if now - self.last_word_at < PAIR_SECONDS and not listening else []
        command = command_of(result, self.lang, before, listening, self.table)
        heard = heard_words(result)
        if command:
            print(f"🗣️ Heard: {' '.join(f'{w} {c:.2f}' for w, c in before + heard)}")
            self.last_words = []
            self.listening_until, self.green_shown = 0.0, False
            return command
        if heard:
            self.last_words, self.last_word_at = (before + heard)[-CARRIED_WORDS:], now
        if heard and listening and not wake_heard(result, self.lang):
            # Something else than a question said after "robot": no longer listening
            self.listening_until, self.last_words = 0.0, []
            if self.green_shown:
                self.green_shown = False
                return LISTENING_OFF
            return None
        if wake_heard(result, self.lang):
            # "Robot" alone: the robot listens for the question
            self.listening_until = now + LISTEN_SECONDS
            if not self.green_shown:
                self.green_shown = True
                print(f"🗣️ \"Robot\" heard ({' '.join(f'{w} {c:.2f}' for w, c in heard)}): the robot listens")
                return LISTENING
        return None

    def _accept(self, data):
        if self.recognizer.AcceptWaveform(data):
            result = json.loads(self.recognizer.Result())
            if self.is_ringing():
                return self._ringing_check(heard_words(result), final=True)
            return self._command(result)
        if self.is_ringing():
            return self._ringing_partial()
        return None

    def _ringing_partial(self):
        """
        While it rings: "robot" (sure) in the partial result -> LISTENING at
        once (the ringtone is turned down); "robot décroche" / "robot
        raccroche" (or the phrase alone at the end, after "robot") -> the
        command at once, the recognizer starts again.
        """
        try:
            partial = json.loads(self.recognizer.PartialResult())
        except (AttributeError, ValueError):
            return None
        heard = [(w.get("word"), w.get("conf", 0)) for w in partial.get("partial_result", []) if isinstance(w, dict)]
        return self._ringing_check(heard)

    def _ringing_check(self, heard, final=False):
        """
        Words heard while it rings (partial or final result): the command, or
        LISTENING for a sure "robot". The ringtone and its announcement are
        heard all the time: they never turn the green off (only the time).
        """
        if not heard:
            return None
        table = {phrase: command for phrase, command in (self.table or phrase_table(self.lang)).items()
                 if command in RINGING_COMMANDS}
        command = command_of({"result": [{"word": w, "conf": c} for w, c in heard]}, self.lang, table=table)
        if command is None and self.listening:
            # "robot" said before: the phrase anywhere in what is heard (a noise
            # of the room or the end of the ringtone may come after it)
            for phrase, name in table.items():
                size = len(phrase.split())
                for start in range(len(heard) - size + 1):
                    part = heard[start:start + size]
                    if " ".join(w for w, _c in part) == phrase and all(c >= MIN_CONFIDENCE for _w, c in part):
                        command = name
                        break
                if command:
                    break
        if command:
            print(f"🗣️ Heard while it rings: {' '.join(f'{w} {c:.2f}' for w, c in heard)}")
            if not final:
                self.recognizer.Reset()
            self.last_words = []
            self.listening_until, self.green_shown = 0.0, False
            return command
        wake = wake_word(self.lang)
        if not self.green_shown and any(w == wake and c >= WAKE_CONFIDENCE for w, c in heard):
            self.listening_until = time.monotonic() + LISTEN_SECONDS
            self.green_shown = True
            print("🗣️ \"Robot\" heard while it rings: the robot listens")
            return LISTENING
        return None

    def frame(self, data, hearing):
        """
        One frame of 100 ms; hearing: a sound is heard (sound_level.py).
        Returns a command, LISTENING / LISTENING_OFF (green of the robot) or None.
        """
        if self.recognizer is None or time.monotonic() < self.muted_until:
            return None
        if self.green_shown and not self.listening and self.is_ringing():
            # While it rings the sound never stops: green off when the time is over
            self.green_shown = False
            return LISTENING_OFF
        if self.grammar_changed and not self.feeding:
            # New stations or contacts: between two sentences only
            try:
                self._new_recognizer()
            except Exception as e:
                print(f"⚠️ Voice commands: new words not taken ({e})")
                self.grammar_changed = False
        if not hearing and not self.feeding:
            self.preroll.append(data)
            return self._listening_over()
        events = []
        if not self.feeding:
            self.feeding, self.tail = True, 0
            for old in self.preroll:
                events.append(self._accept(old))
            self.preroll.clear()
        events.append(self._accept(data))
        if hearing:
            self.tail = 0
        else:
            self.tail += 1
            if self.tail >= TAIL_FRAMES:
                self.feeding = False
                final = json.loads(self.recognizer.FinalResult())
                if self.is_ringing():
                    events.append(self._ringing_check(heard_words(final), final=True))
                else:
                    events.append(self._command(final))
        events = [e for e in events if e]
        commands = [e for e in events if e not in (LISTENING, LISTENING_OFF)]
        if commands:
            return commands[-1]
        return events[-1] if events else self._listening_over()

    def _listening_over(self):
        """LISTENING_OFF once the robot listened long enough without a question."""
        if self.green_shown and not self.listening and not self.feeding:
            self.green_shown = False
            return LISTENING_OFF
        return None
