# ============================================
# FILE: robot_answers.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sentences said by the robot to the spoken commands (voice_commands.py), in
the language of the Raspberry:

  - time: "Il est 14 heures et 35 minutes" (local time of the Raspberry);
  - weather: temperature now, then what is left of the day, hour by hour
    (weather of the server, server-weather.js: place of config.py,
    Open-Meteo): at night the rest of the night and the day to come, in
    the morning the rest of the day, in the afternoon until this evening,
    in the evening tonight and tomorrow; the hour of the first rain;
    without the hours (older server), the forecast of the whole day;
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
# Parts of the day (hours of the place): the night until NIGHT_END, the
# evening from EVENING_START; the afternoon from NOON. The day said lasts
# until DAY_END (the hours after it belong to the evening and the night).
NIGHT_END = 6
NOON = 12
EVENING_START = 18
DAY_END = 21
# Sky of several hours: the worst one if it lasts (storm, snow, rain), else
# the one seen most often
WORST_SKIES = ("storm", "snow", "rain")


def hour_text(hour, lang=None):
    """An hour said with a number: "15 heures", "3 PM", "las 15"."""
    lang = lang or language()
    if lang == "en":
        return t("voice.atHour", hour=hour % 12 or 12, period="AM" if hour < 12 else "PM")
    return t("voice.atHour", hour=hour)


def valid_hours(day):
    """Hours of a day of the server ({hour, temperature, icon, isDay, rain}) that can be said."""
    hours = day.get("hours") if isinstance(day, dict) else None
    return [h for h in hours or [] if isinstance(h, dict) and isinstance(h.get("hour"), int)
            and isinstance(h.get("temperature"), (int, float)) and h.get("icon") in SKIES]


def sky_of(hours, night=False):
    """Sky said of several hours ("grand soleil", "ciel dégagé" at night...)."""
    icons = [h["icon"] for h in hours]
    worst = next((icon for icon in WORST_SKIES if icons.count(icon) >= min(2, len(icons))), None)
    icon = worst or max(SKIES, key=lambda name: (icons.count(name), -SKIES.index(name)))
    return t("voice.sky.clearNight" if icon == "clear" and night else "voice.sky." + icon)


def range_text(low, high):
    low, high = round(low), round(high)
    return t("voice.rangeOne", t=low) if low == high else t("voice.range", min=low, max=high)


def period_sentence(key, hours, night=False):
    """"Pour le reste de la journée : quelques nuages, entre 12 et 16 degrés." (+ the first rain)."""
    temperatures = [h["temperature"] for h in hours]
    parts = [t(key, sky=sky_of(hours, night), range=range_text(min(temperatures), max(temperatures)))]
    rainy = [h for h in hours if isinstance(h.get("rain"), (int, float)) and h["rain"] >= RAIN_FROM]
    if rainy:
        parts.append(t("voice.weatherRainAt", hour=hour_text(rainy[0]["hour"]), rain=round(max(h["rain"] for h in rainy))))
    return parts


def day_sentence(key, day):
    """Forecast of a whole day ({icon, min, max, rain}): "Demain : grand soleil, entre 8 et 19 degrés."."""
    if not (isinstance(day, dict) and day.get("icon") in SKIES
            and isinstance(day.get("min"), (int, float)) and isinstance(day.get("max"), (int, float))):
        return []
    parts = [t(key, sky=t("voice.sky." + day["icon"]), range=range_text(day["min"], day["max"]))]
    rain = day.get("rain")
    if isinstance(rain, (int, float)) and rain >= RAIN_FROM:
        parts.append(t("voice.weatherRain", rain=round(rain)))
    return parts


def rest_of_day(weather, now):
    """
    What is left of the day, from the hours of the server (today and
    tomorrow; now: "2026-10-19T15", hour of the place). None without them.
    """
    days = weather.get("days")
    if not isinstance(days, list) or not days:
        return None
    hour = None
    if isinstance(weather.get("now"), str) and weather["now"][-2:].isdigit():
        hour = int(weather["now"][-2:])
    elif now is not None:
        hour = now.hour
    if hour is None:
        return None
    today = valid_hours(days[0])
    tomorrow = days[1] if len(days) > 1 else None
    after = [h for h in today if h["hour"] > hour]
    parts = []
    if hour < NIGHT_END:
        night = [h for h in after if h["hour"] < NIGHT_END]
        day = [h for h in after if NIGHT_END <= h["hour"] <= DAY_END]
        if night:
            parts += period_sentence("voice.weatherTonight", night, night=True)
        if day:
            parts += period_sentence("voice.weatherDuringDay", day)
    elif hour < EVENING_START:
        day = [h for h in after if h["hour"] <= DAY_END]
        if day:
            parts += period_sentence("voice.weatherRestOfDay" if hour < NOON else "voice.weatherUntilEvening", day)
    else:
        night = after + [h for h in valid_hours(tomorrow) if h["hour"] < NIGHT_END]
        if night:
            parts += period_sentence("voice.weatherTonight", night, night=True)
        parts += day_sentence("voice.weatherTomorrow", tomorrow)
    return parts or None


def weather_sentence(weather, now=None):
    """
    Weather said by the robot, from the answer of the server ({available,
    temperature, place, today: {icon, min, max, rain}, now, days, reason}):
    the temperature now, then what is left of the day (rest_of_day), or the
    forecast of the whole day without the hours. now: local time (datetime),
    used only if the server does not give the hour of the place.
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
    rest = rest_of_day(weather, now)
    parts += rest if rest is not None else day_sentence("voice.weatherToday", weather.get("today"))
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
