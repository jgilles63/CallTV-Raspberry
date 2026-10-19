# ============================================
# FILE: radio.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Internet radio asked by voice to the robot (voice_commands.py): "Robot, mets
la radio" (last station listened to, else the first one), "Robot, radio
101.2" (the station of that frequency), "Robot ... stop".

The stations are those of the country of the TV (radio_stations.py: the
country of the settings page, else the language), or one's own list in
config.RADIO_STATIONS (name, FM frequency, address of the stream); the
frequency is only a name for the voice, the sound comes from the internet. A station can also be asked by its name ("Robot, mets
France Inter"). Played on the speaker of the ringtone (USB speaker): ffmpeg
reads the stream, aplay plays it, at the volume of the radio
(tts_audio.radio_volume, 0 to 100 %: slider of the radio page, settings
page, "Robot, volume 5"; the voice of the robot has its own volume,
tts_audio.voice_level). While the robot listens to a question the radio is
turned down to DUCK_VOLUME; while it speaks the radio is paused (the speaker plays one sound
at a time), then it goes on. A call, the button or the "Stop" button of the
TV page stop it. The radio page of the TV (ROADMAP 2.18) chooses a station
and plays / stops it too (agent.py).

The sound goes from ffmpeg to aplay through the agent (a thread): its level
is measured on the way, every LEVEL_MS (levels(), 0 to 100), for the wave
drawn on the radio page.

The last station is kept in radio_station.txt (application folder).
"""

import array
import collections
import math
import re
import subprocess
import sys
import threading

import config
import radio_stations
import tts_audio

# FM band: frequencies accepted in config.RADIO_STATIONS
MIN_FREQUENCY = 87.5
MAX_FREQUENCY = 108.0
LAST_STATION_FILE_NAME = "radio_station.txt"
# Sound given by ffmpeg to aplay
RATE = 44100
CHANNELS = 2
# Volume (%) of the radio while the robot listens to a question (decision of
# 18/10/2026; never louder than the radio itself)
DUCK_VOLUME = 10
# Level of the sound (wave of the radio page): one every LEVEL_MS, the last
# MAX_LEVELS kept; SILENT_DB and quieter = 0
LEVEL_MS = 50
CHUNK_BYTES = RATE * CHANNELS * 2 * LEVEL_MS // 1000
MAX_LEVELS = 40
SILENT_DB = -50


def level_of(chunk):
    """Level 0 to 100 of a piece of sound (s16le): its peak, on a scale of decibels."""
    samples = array.array("h")
    samples.frombytes(chunk[:len(chunk) - len(chunk) % 2])
    if sys.byteorder == "big":
        samples.byteswap()
    if not samples:
        return 0
    peak = max(max(samples), -min(samples))
    if peak <= 0:
        return 0
    decibels = 20 * math.log10(peak / 32768)
    return max(0, min(100, round((decibels - SILENT_DB) * 100 / -SILENT_DB)))


def frequency_text(value):
    """"101.2" for 101.2 (one decimal), or None if not an FM frequency."""
    try:
        number = round(float(value), 1)
    except (TypeError, ValueError):
        return None
    return f"{number:.1f}" if MIN_FREQUENCY <= number <= MAX_FREQUENCY else None


def stations():
    """
    Valid stations: config.RADIO_STATIONS if it is a list (one's own),
    else those of the country of the TV: [{name, frequency ("101.2"), url}].
    """
    own = getattr(config, "RADIO_STATIONS", None)
    listed = own if isinstance(own, list) else radio_stations.stations_for(
        getattr(config, "WEATHER_COUNTRY", None), getattr(config, "LANGUAGE", None))
    found, seen = [], set()
    for station in listed:
        if not isinstance(station, dict):
            continue
        name = re.sub(r"\s+", " ", str(station.get("name") or "")).strip()[:40]
        frequency = frequency_text(station.get("frequency"))
        url = str(station.get("url") or "").strip()
        if not name or not frequency or frequency in seen or not re.match(r"^https?://[^\s]+$", url):
            continue
        seen.add(frequency)
        found.append({"name": name, "frequency": frequency, "url": url})
    return found


def find(frequency):
    """Station of a frequency ("101.2"), or None."""
    return next((s for s in stations() if s["frequency"] == frequency_text(frequency)), None)


def last_station_file():
    return config.BASE_DIR / LAST_STATION_FILE_NAME


def default_station():
    """Station of "mets la radio": the last one listened to, else the first one."""
    try:
        station = find(last_station_file().read_text(encoding="utf-8").strip())
    except (OSError, AttributeError):
        station = None
    all_stations = stations()
    return station or (all_stations[0] if all_stations else None)


class Radio:
    """One station at a time: ffmpeg (stream) -> aplay (speaker)."""

    def __init__(self, popen=subprocess.Popen):
        self.popen = popen
        self.station = None
        self.paused = False
        self.processes = []
        self.sound_levels = collections.deque(maxlen=MAX_LEVELS)

    @property
    def playing(self):
        return self.station is not None and not self.paused

    @property
    def on(self):
        """A station is chosen (playing or paused while the robot speaks)."""
        return self.station is not None

    def play(self, station):
        """Plays a station (stops the one playing)."""
        self._kill()
        self.station, self.paused = station, False
        try:
            last_station_file().write_text(station["frequency"] + "\n", encoding="utf-8")
        except OSError:
            pass
        self._start()

    def _start(self):
        card = tts_audio.find_ringing_card()
        tts_audio.set_speaker_volume()
        print(f"📻 Radio: {self.station['name']} ({self.station['frequency']})")
        try:
            reader = self.popen(
                ["ffmpeg", "-nostdin", "-loglevel", "error",
                 "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "10",
                 "-protocol_whitelist", "http,https,tcp,tls,crypto",
                 "-i", self.station["url"], "-vn", "-f", "s16le", "-ac", str(CHANNELS), "-ar", str(RATE), "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            player = self.popen(
                ["aplay", "-q", "-D", tts_audio.playback_device(card), "-t", "raw", "-f", "S16_LE",
                 "-c", str(CHANNELS), "-r", str(RATE)],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.processes = [reader, player]
            self.sound_levels.clear()
            if reader.stdout is not None and player.stdin is not None:
                threading.Thread(target=self.pump, args=(reader.stdout, player.stdin), daemon=True).start()
        except OSError as e:
            print(f"⚠️ Radio not started ({e})")
            self.processes = []

    def pump(self, source, sink):
        """ffmpeg -> aplay (thread): the level of each piece of sound is kept on the way."""
        try:
            while True:
                chunk = source.read(CHUNK_BYTES)
                if not chunk:
                    break
                self.sound_levels.append(level_of(chunk))
                sink.write(chunk)
                sink.flush()
        except (OSError, ValueError):
            pass  # radio stopped or paused: the processes are gone
        finally:
            for stream in (sink, source):
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass

    def levels(self):
        """Levels of the sound (0 to 100) measured since the last time (oldest first)."""
        taken = []
        while self.sound_levels:
            taken.append(self.sound_levels.popleft())
        return taken

    def _kill(self):
        for process in self.processes:
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        self.processes = []

    def stop(self):
        """Stops the radio (stop, a call)."""
        if self.station is not None:
            print("📻 Radio stopped")
        self._kill()
        self.station, self.paused = None, False

    def pause(self):
        """Paused while the robot speaks (the speaker plays one sound at a time)."""
        if self.playing:
            self._kill()
            self.paused = True

    def resume(self):
        """Goes on after the robot spoke."""
        if self.station is not None and self.paused:
            self.paused = False
            self._start()

    def duck(self):
        """Turned down while the robot listens to a question."""
        if self.playing:
            tts_audio.set_speaker_volume(min(DUCK_VOLUME, tts_audio.radio_volume()))

    def unduck(self):
        if self.playing:
            tts_audio.set_speaker_volume()

    def check(self):
        """
        The stream stopped by itself (internet lost for long, station gone):
        the radio is off. True if it was.
        """
        if self.playing and self.processes and any(p.poll() is not None for p in self.processes):
            print("⚠️ Radio stream ended")
            self._kill()
            self.station = None
            return True
        return False
