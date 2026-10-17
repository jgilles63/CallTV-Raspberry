# ============================================
# FILE: diagnostics.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Health report of the Raspberry ("état des lieux"), to troubleshoot it
remotely.

run_checks() returns a report that does not depend on the language:
    {
      "version": 1,
      "time": "2026-10-12T10:00:00+00:00",
      "checks": [{"id": "hdmi", "status": "ok", "value": "connected"}, ...],
      "logs": {"tv-control": [...], "chromium-autolaunch": [...]},
    }
status is "ok", "warn", "fail" or "info". The labels are translated by
whoever shows the report (format_report() here, admin.js on the server).

The report never contains secrets: no identity secret, no Wi-Fi name or
password, no address. Only the last error lines of the logs are included.

Used by:
- agent.py, when the server asks for it (diagnose_request);
- diagnose.sh, directly on the Raspberry.
"""

import datetime
import glob
import json
import os
import platform
import re
import shutil
import socket
import subprocess
from urllib.parse import urlparse

import config
from i18n import t

REPORT_VERSION = 1

SERVICES = (("service.tvControl", "tv-control.service"),
            ("service.chromium", "chromium-autolaunch.service"))
# Services whose last errors are shown (the self-repair actions are shown too)
LOG_SERVICES = ("tv-control.service", "chromium-autolaunch.service", "appelermamie-selfheal.service",
                "appelermamie-update.service")

# State of the self-repair (selfheal.py)
SELFHEAL_STATE_FILE = "/var/lib/appelermamie/selfheal.json"

# Result of the last remote update (update.sh)
UPDATE_STATE_FILE = "/var/lib/appelermamie/update.json"

# Error lines kept from the logs of each service
LOG_LINES_KEPT = 15
LOG_LINE_MAX_LENGTH = 200
LOG_ERROR_MARKERS = ("❌", "⚠️", "⛔", "Traceback", "Error", "ERROR", "error", "failed", "Failed")
# Harmless messages of Chromium (kiosk without D-Bus session, Google services,
# screen refresh): not errors of the project, they would hide the real ones
LOG_NOISE = ("dbus/", "google_apis/gcm/", "gl_surface_presentation_helper", "Failed to connect to the bus")

# vcgencmd get_throttled bits: (bit, flag) — "now" bits, then "since boot"
THROTTLED_NOW = ((0, "underVoltage"), (1, "freqCapped"), (2, "throttled"), (3, "softTempLimit"))
THROTTLED_SINCE_BOOT = ((16, "underVoltage"), (17, "freqCapped"), (18, "throttled"), (19, "softTempLimit"))

# Camera drivers that are not cameras (video codecs and image processors of the Pi)
USB_CAMERA_DRIVER = "uvcvideo"

COMMAND_TIMEOUT = 15

# Places of iw when it is not in the PATH (diagnose.sh run by a user)
IW_PATHS = ("/usr/sbin/iw", "/sbin/iw")


def run(command, timeout=COMMAND_TIMEOUT, shell=False):
    """Runs a command and returns its output (stdout + stderr), or None if it fails to run."""
    try:
        result = subprocess.run(command, shell=shell, capture_output=True, text=True,
                                timeout=timeout, errors="replace")
        return (result.stdout or "") + (result.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return None


def read_file(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def check(check_id, status, value=""):
    return {"id": check_id, "status": status, "value": str(value)}


# ---------------------------------------------------------
# System
# ---------------------------------------------------------

def check_model():
    model = read_file("/proc/device-tree/model")
    return check("system.model", "info", model.strip("\x00\n ") if model else "?")


def check_os():
    text = read_file("/etc/os-release") or ""
    match = re.search(r'^PRETTY_NAME="?([^"\n]*)"?', text, re.M)
    name = match.group(1) if match else "?"
    return check("system.os", "info", f"{name} — Linux {platform.release()}")


def check_uptime():
    text = read_file("/proc/uptime")
    if not text:
        return check("system.uptime", "info", "?")
    seconds = int(float(text.split()[0]))
    days, rest = divmod(seconds, 86400)
    return check("system.uptime", "info", f"{days}d {rest // 3600:02d}:{rest % 3600 // 60:02d}")


def check_services():
    results = []
    for check_id, service in SERVICES:
        output = run(["systemctl", "is-active", service])
        state = output.strip() if output else "?"
        results.append(check(check_id, "ok" if state == "active" else "fail", state))
    return results


def check_chromium_version():
    for command in ("chromium", "chromium-browser"):
        output = run([command, "--version"])
        if output and "chromium" in output.lower():
            return check("version.chromium", "info", output.strip().splitlines()[-1])
    return check("version.chromium", "fail", "?")


def check_selfheal():
    """Self-repair active (timer), and its last action ("2026-10-12 04:00 reboot (nightly)")."""
    output = run(["systemctl", "is-active", "appelermamie-selfheal.timer"])
    state = output.strip() if output else "?"
    value = state
    try:
        history = json.loads(read_file(SELFHEAL_STATE_FILE) or "{}").get("history") or []
        if history:
            last = history[-1]
            when = datetime.datetime.fromtimestamp(float(last["time"])).strftime("%Y-%m-%d %H:%M")
            value += f", {when} {last['action']} ({last['reason']}), {len(history)}"
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    return check("selfheal", "ok" if state == "active" else "warn", value)


def check_version():
    """Installed version (VERSION file written by install.sh)."""
    value = (read_file(str(config.BASE_DIR / "VERSION")) or "").strip() or "unknown"
    return check("version", "info", value)


def check_update():
    """Remote updates possible (appelermamie-update.path), and the last one."""
    output = run(["systemctl", "is-active", "appelermamie-update.path"])
    state = output.strip() if output else "?"
    value, status = state, "ok" if state == "active" else "warn"
    try:
        last = json.loads(read_file(UPDATE_STATE_FILE) or "{}")
        if last:
            when = datetime.datetime.fromtimestamp(float(last["time"])).strftime("%Y-%m-%d %H:%M")
            value += f", {when} {last['from']} -> {last['to']} {last['result']}"
            if last.get("reason"):
                value += f" ({last['reason']})"
            if last["result"] in ("failed", "rolled back"):
                status = "warn"
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    return check("update", status, value)


def check_watchdog():
    """Hardware watchdog of systemd (restarts the Raspberry if everything freezes)."""
    output = run(["systemctl", "show", "-p", "RuntimeWatchdogUSec"]) or ""
    value = output.strip().partition("=")[2] or "?"
    active = value not in ("?", "0", "infinity")
    return check("system.watchdog", "ok" if active else "warn", value)


# ---------------------------------------------------------
# Network
# ---------------------------------------------------------

def check_server():
    """Server used, and whether its port answers (the address is not resolved in the report)."""
    url = urlparse(config.SERVER_URL)
    port = url.port or (443 if url.scheme == "wss" else 80)
    try:
        with socket.create_connection((url.hostname, port), timeout=5):
            return check("network.server", "ok", config.SERVER_URL)
    except OSError as e:
        return check("network.server", "fail", f"{config.SERVER_URL} ({type(e).__name__})")


def check_interfaces():
    """Network interfaces that are up (the Wi-Fi name is never read)."""
    up = []
    for path in sorted(glob.glob("/sys/class/net/*/operstate")):
        name = path.split("/")[-2]
        if name != "lo" and (read_file(path) or "").strip() == "up":
            up.append(name)
    return check("network.interfaces", "ok" if up else "fail", ", ".join(up) or "-")


def check_wifi():
    """Wi-Fi signal in dBm (from /proc/net/wireless): -50 very good, -70 fair, -80 poor."""
    text = read_file("/proc/net/wireless") or ""
    for line in text.splitlines()[2:]:
        fields = line.split()
        if len(fields) >= 4:
            try:
                level = float(fields[3].rstrip("."))
            except ValueError:
                continue
            status = "ok" if level >= -67 else ("warn" if level >= -80 else "fail")
            return check("network.wifi", status, f"{fields[0].rstrip(':')} {level:.0f} dBm")
    return check("network.wifi", "info", "-")


def iw_command():
    """iw is in /usr/sbin: not in the PATH of a user who runs diagnose.sh by hand."""
    if shutil.which("iw"):
        return "iw"
    return next((path for path in IW_PATHS if os.path.exists(path)), "iw")


def check_wifi_powersave():
    """Wi-Fi power saving: "off" expected (it causes disconnections on the Raspberry)."""
    output = run([iw_command(), "dev", "wlan0", "get", "power_save"])
    match = re.search(r"Power save:\s*(\w+)", output or "")
    if not match:
        return check("network.powersave", "info", "-")
    return check("network.powersave", "ok" if match.group(1) == "off" else "warn", match.group(1))


# ---------------------------------------------------------
# TV, camera, sound, mouse
# ---------------------------------------------------------

def check_hdmi():
    states = []
    for path in sorted(glob.glob("/sys/class/drm/*HDMI*/status")):
        connector = path.split("/")[-2].split("-", 1)[-1]
        states.append((connector, (read_file(path) or "?").strip()))
    if not states:
        return check("hdmi", "fail", "?")
    connected = [name for name, state in states if state == "connected"]
    value = ", ".join(f"{name}: {state}" for name, state in states)
    return check("hdmi", "ok" if connected else "fail", value)


def check_screen():
    """Resolution of the screen (wlr-randr): 1920 x 1080 expected on a 4K TV (display_mode.py)."""
    import display_mode
    modes = display_mode.current_mode()
    if not modes:
        return check("screen", "info", "-")
    value = ", ".join(f"{name}: {w}x{h} {refresh:g} Hz" for name, (w, h, refresh) in modes)
    too_big = any(w > display_mode.MAX_WIDTH for _, (w, _h, _r) in modes)
    wanted = getattr(config, "SCREEN_MODE", "1080p") == "1080p"
    return check("screen", "warn" if too_big and wanted else "ok", value)


def check_cec(skip=False):
    """
    Power status of the TV seen through HDMI-CEC ("on", "standby"...) and the
    physical address of the Raspberry (3.0.0.0 = input 3), with cec-ctl
    (tv_control.py). Declares the Raspberry to the TV if needed (remote control).
    """
    if skip:
        return check("cec", "info", "skipped")
    import tv_control
    adapter, address = tv_control.ensure_cec_ready()
    if adapter is None:
        return check("cec", "fail", "no CEC adapter")
    power = tv_control.tv_power(adapter)
    if power is None:
        return check("cec", "fail", f"no answer ({address})")
    return check("cec", "ok" if power == "on" else "warn", f"{power} ({address})")


def check_camera():
    names = []
    for path in sorted(glob.glob("/sys/class/video4linux/video*")):
        driver = os.path.basename(os.path.realpath(f"{path}/device/driver"))
        name = (read_file(f"{path}/name") or "").strip()
        # The kernel cuts the name at 31 characters ("Trust ... Webcam: Tru"):
        # the cut repetition after ": " is removed
        head, _, tail = name.partition(": ")
        if tail and head.startswith(tail):
            name = head
        if driver == USB_CAMERA_DRIVER and name and name not in names:
            names.append(name)
    return check("camera", "ok" if names else "fail", ", ".join(names) or "-")


def check_microphone():
    """Sound cards that can record (a webcam microphone, a USB speaker with a microphone...)."""
    names = []
    text = read_file("/proc/asound/cards") or ""
    for line in text.splitlines():
        match = re.match(r"^\s*(\d+)\s+\[(\S+)\s*\]:\s+(\S+)\s+-\s+(.*)$", line)
        if match and glob.glob(f"/proc/asound/card{match.group(1)}/pcm*c"):
            names.append(match.group(4).strip())
    return check("microphone", "ok" if names else "fail", ", ".join(names) or "-")


def check_call_audio():
    """Current default output of PipeWire: where the call sound is played (call_audio.py)."""
    from call_audio import default_sink_name
    name = default_sink_name()
    mode = getattr(config, "CALL_AUDIO_OUTPUT", "auto")
    return check("callAudio", "info" if name else "warn", f"{name or '?'} (CALL_AUDIO_OUTPUT={mode})")


def check_speaker():
    from tts_audio import find_ringing_card
    card = find_ringing_card()
    if card:
        return check("speaker", "ok", f"{' '.join(card['name'].split())} ({card['id']})")
    return check("speaker", "warn", "HDMI")


def check_mouse():
    """Pointer devices seen by the kernel (the answer button of the agent)."""
    names = []
    text = read_file("/proc/bus/input/devices") or ""
    for block in text.split("\n\n"):
        name = re.search(r'^N: Name="([^"]*)"', block, re.M)
        handlers = re.search(r"^H: Handlers=(.*)$", block, re.M)
        if name and handlers and re.search(r"\bmouse\d+", handlers.group(1)):
            names.append(name.group(1))
    return check("mouse", "ok" if names else "fail", ", ".join(names) or "-")


# ---------------------------------------------------------
# Resources
# ---------------------------------------------------------

def check_disk():
    try:
        usage = shutil.disk_usage(str(config.BASE_DIR) if os.path.isdir(config.BASE_DIR) else "/")
    except OSError:
        return check("disk", "fail", "?")
    gb = 1024 ** 3
    free_ratio = usage.free / usage.total
    status = "ok" if free_ratio >= 0.1 and usage.free >= gb else ("warn" if usage.free >= gb / 4 else "fail")
    return check("disk", status, f"{usage.free / gb:.1f} / {usage.total / gb:.1f} GB ({free_ratio:.0%})")


def check_memory():
    text = read_file("/proc/meminfo") or ""
    values = dict(re.findall(r"^(\w+):\s+(\d+)", text, re.M))
    try:
        total, available = int(values["MemTotal"]), int(values["MemAvailable"])
    except (KeyError, ValueError):
        return check("memory", "info", "?")
    ratio = available / total
    status = "ok" if ratio >= 0.15 else ("warn" if ratio >= 0.05 else "fail")
    return check("memory", status, f"{available // 1024} / {total // 1024} MB ({ratio:.0%})")


def check_temperature():
    text = read_file("/sys/class/thermal/thermal_zone0/temp")
    try:
        celsius = int(text.strip()) / 1000
    except (AttributeError, ValueError):
        return check("temperature", "info", "?")
    status = "ok" if celsius < 70 else ("warn" if celsius < 80 else "fail")
    return check("temperature", status, f"{celsius:.1f} °C")


def check_power():
    """
    Power supply and overheating (vcgencmd get_throttled). The value keeps the
    raw code, followed by the decoded flags: "now:underVoltage" (happening now)
    or "boot:underVoltage" (happened since startup).
    """
    output = run(["vcgencmd", "get_throttled"])
    match = re.search(r"throttled=(0x[0-9a-fA-F]+)", output or "")
    if not match:
        return check("power", "info", "?")
    code = int(match.group(1), 16)
    flags = [f"now:{flag}" for bit, flag in THROTTLED_NOW if code & (1 << bit)]
    flags += [f"boot:{flag}" for bit, flag in THROTTLED_SINCE_BOOT if code & (1 << bit)]
    status = "fail" if code & 0b1111 else ("warn" if code else "ok")
    return check("power", status, " ".join([match.group(1)] + flags))


# ---------------------------------------------------------
# Logs
# ---------------------------------------------------------

def error_lines(service):
    """Last error lines of a service (journalctl), shortened."""
    output = run(["journalctl", "-u", service, "-n", "500", "--no-pager", "-o", "short-iso"])
    if output is None:
        return ["?"]
    lines = [line for line in output.splitlines()
             if any(marker in line for marker in LOG_ERROR_MARKERS)
             and not any(noise in line for noise in LOG_NOISE)]
    return [line[:LOG_LINE_MAX_LENGTH] for line in lines[-LOG_LINES_KEPT:]]


# ---------------------------------------------------------
# Report
# ---------------------------------------------------------

def safe(function, *args):
    """A check that crashes must not stop the others."""
    try:
        return function(*args)
    except Exception as e:
        return check(function.__name__.replace("check_", ""), "fail", f"{type(e).__name__}: {e}"[:LOG_LINE_MAX_LENGTH])


def run_checks(skip_cec=False):
    """
    Runs all the checks (a few seconds).
    skip_cec: True during a call, so that the TV is not disturbed.
    """
    checks = [safe(check_version), safe(check_update), safe(check_model), safe(check_os), safe(check_uptime),
              safe(check_watchdog)]
    services = safe(check_services)
    checks += services if isinstance(services, list) else [services]
    checks += [
        safe(check_selfheal), safe(check_chromium_version),
        safe(check_server), safe(check_interfaces), safe(check_wifi), safe(check_wifi_powersave),
        safe(check_hdmi), safe(check_screen), safe(check_cec, skip_cec),
        safe(check_camera), safe(check_microphone), safe(check_speaker), safe(check_call_audio), safe(check_mouse),
        safe(check_disk), safe(check_memory), safe(check_temperature), safe(check_power),
    ]
    return {
        "version": REPORT_VERSION,
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "checks": checks,
        "logs": {service: error_lines(service) for service in LOG_SERVICES},
    }


STATUS_ICONS = {"ok": "✅", "warn": "⚠️", "fail": "❌", "info": "ℹ️"}


def format_value(item):
    """Value of a check; the power flags ("now:underVoltage") are translated."""
    value = item.get("value", "")
    if item.get("id") != "power":
        return value
    words = []
    for word in value.split():
        when, _, flag = word.partition(":")
        words.append(t(f"diag.power.{when}", flag=t(f"diag.flag.{flag}")) if flag else word)
    return " ".join(words)


def format_report(report):
    """Text of the report, in the language of the Raspberry (config.LANGUAGE)."""
    lines = [t("diag.title", device_id=config.RASPBERRY_ID or "?", time=report.get("time", "?")), ""]
    for item in report.get("checks", []):
        icon = STATUS_ICONS.get(item.get("status"), "•")
        label = t(f"diag.check.{item.get('id')}")
        lines.append(f"{icon} {label} : {format_value(item)}")
    for service, log_lines in report.get("logs", {}).items():
        lines += ["", t("diag.logs", service=service)]
        lines += [f"  {line}" for line in log_lines] or [f"  {t('diag.noErrors')}"]
    return "\n".join(lines)


if __name__ == "__main__":
    # Run by diagnose.sh: report in the language of the Raspberry,
    # or as JSON with --json
    import json
    import sys

    from identity import load_identity

    try:
        load_identity()
    except SystemExit:
        pass  # without identity, the report is still useful
    result = run_checks()
    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_report(result))
