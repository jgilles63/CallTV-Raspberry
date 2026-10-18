# ============================================
# FILE: robot_answers.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sentences said by the robot to the spoken commands (voice_commands.py), in
the language of the Raspberry:

  - time: "Il est 14 heures et 35 minutes" (local time of the Raspberry);
  - weather: temperature now and forecast of the day, from the weather of
    the server (server-weather.js: place of config.py, Open-Meteo);
  - health ("Robot, comment ça va ?"): the health report of the Raspberry
    (diagnostics.py), what fails or should be checked, and a few figures.

Texts in i18n.py ("voice.*" keys); numbers written as digits (the voice of
gTTS reads them).
"""

import re

from i18n import language, t


def time_sentence(now, lang=None):
    """Time said by the robot, e.g. "Il est 14 heures et 35 minutes."."""
    lang = lang or language()
    hours, minutes = now.hour, now.minute
    if lang == "en":
        hour12 = hours % 12 or 12
        period = "AM" if hours < 12 else "PM"
        if minutes == 0:
            return t("voice.timeOClock", hours=hour12, period=period)
        return t("voice.time", hours=hour12, minutes=f"{minutes:02d}", period=period)
    if lang == "es":
        hour12 = hours % 12 or 12
        key = "voice.timeOne" if hour12 == 1 else "voice.time"
        if minutes == 0:
            key += "OClock"
        return t(key, hours=hour12, minutes=minutes)
    # French: 24 hours, "minuit" and "midi", "heure" / "minute" in the singular for 1
    if hours in (0, 12):
        hours_text = t("voice.midnight" if hours == 0 else "voice.noon")
    else:
        hours_text = t("voice.hour" if hours == 1 else "voice.hours", n=hours)
    if minutes == 0:
        return t("voice.timeOClock", hours=hours_text)
    minutes_text = t("voice.minute" if minutes == 1 else "voice.minutes", n=minutes)
    return t("voice.time", hours=hours_text, minutes=minutes_text)


SKIES = ("clear", "partly", "cloudy", "rain", "storm", "snow")
# Chance of rain said from this percentage
RAIN_FROM = 30


def weather_sentence(weather):
    """
    Weather said by the robot, from the answer of the server ({available,
    temperature, place, today: {icon, min, max, rain}, reason}).
    """
    if not isinstance(weather, dict) or weather.get("available") is not True:
        reason = weather.get("reason") if isinstance(weather, dict) else None
        return t("voice.weatherNoPlace" if reason in ("no_place", "place_not_found") else "voice.weatherUnknown")
    parts = []
    temperature = weather.get("temperature")
    if isinstance(temperature, (int, float)):
        place = weather.get("place")
        if isinstance(place, str) and place.strip():
            parts.append(t("voice.weatherNowAt", temperature=round(temperature), place=place.strip()[:60]))
        else:
            parts.append(t("voice.weatherNow", temperature=round(temperature)))
    today = weather.get("today")
    if isinstance(today, dict) and today.get("icon") in SKIES \
            and isinstance(today.get("min"), (int, float)) and isinstance(today.get("max"), (int, float)):
        parts.append(t("voice.weatherToday", sky=t("voice.sky." + today["icon"]),
                       min=round(today["min"]), max=round(today["max"])))
        rain = today.get("rain")
        if isinstance(rain, (int, float)) and rain >= RAIN_FROM:
            parts.append(t("voice.weatherRain", rain=round(rain)))
    return " ".join(parts) or t("voice.weatherUnknown")


def said_list(items):
    """"a, b et c" in the language of the Raspberry."""
    if len(items) < 2:
        return "".join(items)
    return ", ".join(items[:-1]) + " " + t("voice.and") + " " + items[-1]


def percent_of(value):
    """The percentage written in a value of a check ("926 / 1847 MB (50%)" -> 50), or None."""
    match = re.search(r"\((\d+)%\)", value or "")
    return int(match.group(1)) if match else None


def check_name(check_id):
    """Name said of a check ("le micro"), the label of the report if none."""
    key = "voice.health." + check_id
    name = t(key)
    return name if name != key else t("diag.check." + check_id)


def health_sentence(report, connected=True):
    """
    How the Raspberry is, said by the robot, from the health report of
    diagnostics.run_checks(): the number of points checked, what fails and
    what should be checked, then the temperature, the free memory and disk,
    and for how long it has been on. connected: registered on the server.
    """
    checks = [c for c in (report or {}).get("checks", []) if isinstance(c, dict)]
    counted = [c for c in checks if c.get("status") in ("ok", "warn", "fail")]
    fails = [check_name(c["id"]) for c in counted if c["status"] == "fail"]
    warns = [check_name(c["id"]) for c in counted if c["status"] == "warn"]
    if not connected:
        fails.insert(0, t("voice.health.network.server"))
    count = len(counted) + (0 if connected else 1)
    if fails:
        parts = [t("voice.healthFail", count=count, items=said_list(fails))]
        if warns:
            parts.append(t("voice.healthAlsoWarn", items=said_list(warns)))
    elif warns:
        parts = [t("voice.healthWarn", count=count, items=said_list(warns))]
    else:
        parts = [t("voice.healthAllGood", count=count)]
    values = {c.get("id"): c.get("value", "") for c in checks}
    temperature = re.match(r"\s*(\d+(?:\.\d+)?)", values.get("temperature", ""))
    memory, disk = percent_of(values.get("memory")), percent_of(values.get("disk"))
    figures = []
    if temperature:
        figures.append(t("voice.healthTemperature", n=round(float(temperature.group(1)))))
    if memory is not None:
        figures.append(t("voice.healthMemory", n=memory))
    if disk is not None:
        figures.append(t("voice.healthDisk", n=disk))
    uptime = re.match(r"(\d+)d (\d+):", values.get("system.uptime", ""))
    if uptime:
        days, hours = int(uptime.group(1)), int(uptime.group(2))
        if days:
            figures.append(t("voice.healthUpDay" if days == 1 else "voice.healthUpDays", n=days))
        else:
            figures.append(t("voice.healthUpHour" if hours <= 1 else "voice.healthUpHours", n=max(hours, 1)))
    return " ".join(parts + figures)
