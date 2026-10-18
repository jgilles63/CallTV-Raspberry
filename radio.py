# ============================================
# FILE: radio.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Internet radio asked by voice to the robot (voice_commands.py): "Robot, mets
la radio" (last station listened to, else the first one), "Robot, radio
101.2" (the station of that frequency), "Robot ... stop".

The stations are in config.RADIO_STATIONS (name, FM frequency, address of
the stream); the frequency is only a name for the voice, the sound comes
from the internet. A station can also be asked by its name ("Robot, mets
France Inter"). Played on the speaker of the ringtone (USB speaker): ffmpeg
reads the stream, aplay plays it, at the volume said by voice
(tts_audio.volume_level; set to START_LEVEL when the radio is turned on).
While the robot listens to a question the radio is turned down to
DUCK_LEVEL; while it speaks the radio is paused (the speaker plays one sound
at a time), then it goes on. A call, the button or the "Stop" button of the
TV page stop it.

The last station is kept in radio_station.txt (application folder).
"""

import re
import subprocess

import config
import tts_audio

# FM band: frequencies accepted in config.RADIO_STATIONS
MIN_FREQUENCY = 87.5
MAX_FREQUENCY = 108.0
LAST_STATION_FILE_NAME = "radio_station.txt"
# Sound given by ffmpeg to aplay
RATE = 44100
CHANNELS = 2
# Volume (1 to 10) set when the radio is turned on, and while the robot
# listens to a question (decisions of 18/10/2026)
START_LEVEL = 2
DUCK_LEVEL = 1


def frequency_text(value):
    """"101.2" for 101.2 (one decimal), or None if not an FM frequency."""
    try:
        number = round(float(value), 1)
    except (TypeError, ValueError):
        return None
    return f"{number:.1f}" if MIN_FREQUENCY <= number <= MAX_FREQUENCY else None


def stations():
    """Valid stations of config.RADIO_STATIONS: [{name, frequency ("101.2"), url}]."""
    found, seen = [], set()
    for station in getattr(config, "RADIO_STATIONS", None) or []:
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
                stdin=reader.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if reader.stdout is not None:
                reader.stdout.close()  # aplay holds it now
            self.processes = [reader, player]
        except OSError as e:
            print(f"⚠️ Radio not started ({e})")
            self.processes = []

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
            tts_audio.set_speaker_volume(DUCK_LEVEL)

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
