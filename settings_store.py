# ============================================
# FILE: settings_store.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Settings changed on the TV (settings page of the home screen, gear at the
top right): settings.json in the application folder, applied over config.py
at its end (apply). Only a closed list of settings, each one checked: the
file never holds code, and the page can never change the server, the
identity or anything else (ROADMAP 2.15).

  - LANGUAGE: "fr", "en" or "es";
  - RINGTONE_VOLUME: music of the ringtone under the announcement, level
    1 to 10 on the page (0.1 to 1.0);
  - VOICE_VOLUME: voice of the announcement, level 1 to 13 on the page
    (10 = 100 % = 1.5, the volume of origin; 13 = 130 %);
  - WEATHER_CITY / WEATHER_POSTCODE / WEATHER_COUNTRY: place of the weather.

The radio stations are shown on the page, not changed there (config.py).
The agent writes the file (save) when "Apply" is confirmed on the TV, then
restarts itself (systemd starts it again) if needed.
"""

import json
import os
from pathlib import Path

FILE_NAME = "settings.json"
LANGUAGES = ("fr", "en", "es")
RINGTONE_LEVELS = range(1, 11)
VOICE_LEVELS = range(1, 14)
# Voice of the announcement: level 10 (100 %) = VOICE_VOLUME 1.5
VOICE_STEP = 0.15
PLACE_KEYS = ("WEATHER_CITY", "WEATHER_POSTCODE", "WEATHER_COUNTRY")
PLACE_MAX_LENGTH = {"WEATHER_CITY": 60, "WEATHER_POSTCODE": 12, "WEATHER_COUNTRY": 40}
# Characters kept in a place (same as install.sh)
PLACE_EXTRA_CHARACTERS = " -'.,"


def clean_place(value, key):
    """A place cleaned like install.sh does, or None if empty."""
    if value is None:
        return None
    text = "".join(c for c in str(value).strip()[:PLACE_MAX_LENGTH[key]] if c.isalnum() or c in PLACE_EXTRA_CHARACTERS)
    return text.strip() or None


def ringtone_level(volume):
    """RINGTONE_VOLUME (0.1 to 1.0) -> level 1 to 10 of the page."""
    try:
        return min(10, max(1, round(float(volume) * 10)))
    except (TypeError, ValueError):
        return 2


def voice_level(volume):
    """VOICE_VOLUME -> level 1 to 13 of the page (1.5 -> 10)."""
    try:
        return min(13, max(1, round(float(volume) / VOICE_STEP)))
    except (TypeError, ValueError):
        return 10


def validate(values):
    """
    Settings sent by the page ({"language", "ringtoneLevel", "city",
    "postcode", "country"}, each one optional) -> {config name: value} of the
    valid ones only; anything else is ignored.
    """
    if not isinstance(values, dict):
        return {}
    clean = {}
    if values.get("language") in LANGUAGES:
        clean["LANGUAGE"] = values["language"]
    level = values.get("ringtoneLevel")
    if isinstance(level, int) and not isinstance(level, bool) and level in RINGTONE_LEVELS:
        clean["RINGTONE_VOLUME"] = level / 10
    level = values.get("ringtoneVoiceLevel")
    if isinstance(level, int) and not isinstance(level, bool) and level in VOICE_LEVELS:
        clean["VOICE_VOLUME"] = round(level * VOICE_STEP, 2)
    for key, name in zip(PLACE_KEYS, ("city", "postcode", "country")):
        if name in values and (values[name] is None or isinstance(values[name], str)):
            clean[key] = clean_place(values[name], key)
    return clean


def settings_file(base_dir):
    return Path(base_dir) / FILE_NAME


def load(base_dir):
    """Valid settings of settings.json ({config name: value}), {} if none or broken."""
    try:
        with open(settings_file(base_dir), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    # Checked again: the file may have been edited by hand
    return {key: value for key, value in data.items() if key in validate_saved(data)}


def validate_saved(data):
    """Names of the valid settings of the file (config names)."""
    valid = set()
    if data.get("LANGUAGE") in LANGUAGES:
        valid.add("LANGUAGE")
    volume = data.get("RINGTONE_VOLUME")
    if isinstance(volume, (int, float)) and not isinstance(volume, bool) and 0.1 <= volume <= 1.0:
        valid.add("RINGTONE_VOLUME")
    volume = data.get("VOICE_VOLUME")
    if isinstance(volume, (int, float)) and not isinstance(volume, bool) and VOICE_STEP <= volume <= 13 * VOICE_STEP + 0.001:
        valid.add("VOICE_VOLUME")
    for key in PLACE_KEYS:
        if key in data and (data[key] is None or (isinstance(data[key], str) and clean_place(data[key], key) == data[key])):
            valid.add(key)
    return valid


def save(base_dir, changes):
    """Adds valid changes to settings.json (written in one go); True if saved."""
    current = load(base_dir)
    current.update(changes)
    path = settings_file(base_dir)
    temporary = path.with_suffix(".json.new")
    try:
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    except OSError as e:
        print(f"⚠️ Settings not saved ({e})")
        return False
    return True


def apply(namespace):
    """Called at the end of config.py: settings.json over its values."""
    base_dir = namespace.get("BASE_DIR")
    if base_dir is None:
        return
    for key, value in load(base_dir).items():
        namespace[key] = value
