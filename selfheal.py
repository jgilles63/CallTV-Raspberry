#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Self-repair of the Raspberry ("le Pi se répare tout seul").

Run as root every minute by appelermamie-selfheal.timer (installed by
install.sh in /usr/local/lib/appelermamie/). Only the standard library is
used, and no module of the project is imported (it runs as root).

What it repairs, never during a call:
- Wi-Fi lost (the Raspberry no longer reaches its own box): network restarted
  after 5 min, then every 5 min; Raspberry restarted after 15 min.
  When only the server, or only the Internet access of the box, is down,
  nothing is done: restarting the Raspberry would not help.
- TV page not connected to the server while the agent is: Chromium restarted
  after 3 min (at most every 10 min); Raspberry restarted after 15 min.
- TV page stuck during a call (camera blocked or page frozen: told by the
  server to the agent, displayStuckAt in agent_state.json): Chromium restarted
  once the call is over (at most every 10 min, like the page above).
- Agent not connected while the server is reachable (and not refused by the
  server): agent restarted after 10 min (at most every 10 min).
- Every night at NIGHTLY_REBOOT_HOUR (config.py, 4 h by default; None = never):
  the Raspberry restarts, quietly (the TV is not turned on).
A restart of the Raspberry happens at most once per hour, and never in the
first 10 minutes after startup. A stuck agent is restarted by systemd itself
(WatchdogSec in tv-control.service).

The state is kept in /var/lib/appelermamie/selfheal.json (also read by the
health report, diagnostics.py). Each action is written to the journal:
journalctl -u appelermamie-selfheal
"""

import json
import os
import re
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse

STATE_FILE = "/var/lib/appelermamie/selfheal.json"
AGENT_STATE_NAME = "agent_state.json"

MINUTE = 60
NETWORK_RESTART_AFTER = 5 * MINUTE
NETWORK_RESTART_EVERY = 5 * MINUTE
PAGE_RESTART_AFTER = 3 * MINUTE
PAGE_RESTART_EVERY = 10 * MINUTE
AGENT_RESTART_AFTER = 10 * MINUTE
AGENT_RESTART_EVERY = 10 * MINUTE
REBOOT_AFTER = 15 * MINUTE
REBOOT_EVERY = 60 * MINUTE
NO_REBOOT_AFTER_BOOT = 10 * MINUTE
# The nightly restart happens once: only if the Raspberry has been on for longer
NIGHTLY_MIN_UPTIME = 3 * 60 * MINUTE
# The agent writes its state every 30 s: older than this, it is not trusted
AGENT_STATE_MAX_AGE = 2 * MINUTE
HISTORY_KEPT = 20

# Addresses used to tell "Internet works" from "only our server is down"
INTERNET_PROBES = (("1.1.1.1", 443), ("8.8.8.8", 443))


# ---------------------------------------------------------
# System access (replaced in the tests)
# ---------------------------------------------------------

def run(command):
    """Runs a command; returns its output, or None if it cannot run."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, errors="replace")
        return result.stdout
    except (OSError, subprocess.SubprocessError):
        return None


def read_file(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def can_connect(host, port, timeout=5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def gateway_answers():
    """True if the box (default gateway) answers a ping."""
    route = run(["ip", "-4", "route", "show", "default"]) or ""
    match = re.search(r"default via (\S+)", route)
    if not match:
        return False
    return succeeds(["ping", "-c", "1", "-W", "2", match.group(1)])


def succeeds(command):
    """True if the command runs and ends without error."""
    try:
        return subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30) == 0
    except (OSError, subprocess.SubprocessError):
        return False


def uptime():
    text = read_file("/proc/uptime")
    return float(text.split()[0]) if text else 0.0


def boot_id():
    return (read_file("/proc/sys/kernel/random/boot_id") or "").strip()


def now():
    return time.time()


def local_hour():
    return time.localtime().tm_hour


def act(command):
    """Runs a repair command (systemctl, reboot)."""
    subprocess.call(command)


# ---------------------------------------------------------
# Settings and agent state
# ---------------------------------------------------------

def read_settings(app_dir):
    """SERVER_URL and NIGHTLY_REBOOT_HOUR, read in config.py (not imported: it runs as root)."""
    text = read_file(os.path.join(app_dir, "config.py")) or ""
    url = re.search(r'^SERVER_URL\s*=\s*"([^"]+)"', text, re.M)
    hour = re.search(r"^NIGHTLY_REBOOT_HOUR\s*=\s*(\w+)", text, re.M)
    nightly = 4
    if hour:
        nightly = int(hour.group(1)) if hour.group(1).isdigit() and int(hour.group(1)) < 24 else None
    return (url.group(1) if url else "wss://appelermami.fr"), nightly


def read_agent_state(app_dir):
    """State written by the agent (agent.py), or None if missing or too old."""
    try:
        state = json.loads(read_file(os.path.join(app_dir, AGENT_STATE_NAME)) or "")
    except ValueError:
        return None
    if not isinstance(state, dict) or now() - float(state.get("time", 0)) > AGENT_STATE_MAX_AGE:
        return None
    return state


def network_status(server_url):
    """
    "ok": server reachable; "server": Internet works but not our server;
    "internet": the box answers but has no Internet; "local": the Raspberry
    cannot reach its box (Wi-Fi lost): only this case is repaired.
    """
    url = urlparse(server_url)
    port = url.port or (443 if url.scheme in ("wss", "https") else 80)
    if url.hostname and can_connect(url.hostname, port):
        return "ok"
    if any(can_connect(host, p) for host, p in INTERNET_PROBES):
        return "server"
    if gateway_answers():
        return "internet"
    return "local"


# ---------------------------------------------------------
# Decision
# ---------------------------------------------------------

def load_state():
    try:
        state = json.loads(read_file(STATE_FILE) or "")
        return state if isinstance(state, dict) else {}
    except ValueError:
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.chmod(tmp, 0o644)
    os.replace(tmp, STATE_FILE)


def since(state, problem, present, t):
    """Time since which the problem is present (0 if it is not)."""
    key = f"{problem}Since"
    if not present:
        state.pop(key, None)
        return 0
    state.setdefault(key, t)
    return t - state[key]


def allowed(state, action, every, t):
    return t - state.get(f"last_{action}", 0) >= every


def record(state, action, reason, t):
    state[f"last_{action}"] = t
    state.setdefault("history", []).append({"time": t, "action": action, "reason": reason})
    state["history"] = state["history"][-HISTORY_KEPT:]
    # "⚠️" so that the line is shown in the health report (last errors)
    print(f"⚠️ Self-repair: {action} ({reason})", flush=True)


def check_once(app_dir, state):
    """One pass (every minute). Returns the action done, or None."""
    t = now()
    current_boot = boot_id()
    if state.get("bootId") != current_boot:
        # New start: the problems are counted again from now
        for key in [k for k in state if k.endswith("Since")]:
            del state[key]
        state["bootId"] = current_boot

    server_url, nightly_hour = read_settings(app_dir)
    agent = read_agent_state(app_dir)
    in_call = bool(agent and agent.get("inCall"))
    network = network_status(server_url)
    state["network"] = network
    up = uptime()

    local_down = since(state, "networkDown", network == "local", t)
    page_down = since(state, "pageDown",
                      bool(agent and agent.get("registered") and agent.get("displayConnected") is False), t)
    agent_down = since(state, "agentDown",
                       network == "ok" and not (agent and (agent.get("registered") or agent.get("rejected"))), t)

    if in_call:
        return None

    def reboot(reason):
        if up < NO_REBOOT_AFTER_BOOT or not allowed(state, "reboot", REBOOT_EVERY, t):
            return None
        record(state, "reboot", reason, t)
        save_state(state)
        act(["systemctl", "reboot"])
        return "reboot"

    if local_down >= REBOOT_AFTER and (action := reboot("wifi")):
        return action
    if local_down >= NETWORK_RESTART_AFTER and allowed(state, "network", NETWORK_RESTART_EVERY, t):
        record(state, "network", "wifi", t)
        act(["systemctl", "restart", "NetworkManager"])
        return "network"

    # Stuck after the last restart of the page: not repaired yet
    stuck_at = agent.get("displayStuckAt") if agent else None
    if (isinstance(stuck_at, (int, float)) and stuck_at > state.get("last_page", 0)
            and allowed(state, "page", PAGE_RESTART_EVERY, t)):
        record(state, "page", "page stuck during a call", t)
        act(["systemctl", "restart", "chromium-autolaunch.service"])
        return "page"

    if page_down >= REBOOT_AFTER and (action := reboot("page")):
        return action
    if page_down >= PAGE_RESTART_AFTER and allowed(state, "page", PAGE_RESTART_EVERY, t):
        record(state, "page", "page not connected", t)
        act(["systemctl", "restart", "chromium-autolaunch.service"])
        return "page"

    if agent_down >= AGENT_RESTART_AFTER and allowed(state, "agent", AGENT_RESTART_EVERY, t):
        record(state, "agent", "agent not connected", t)
        act(["systemctl", "restart", "tv-control.service"])
        return "agent"

    if nightly_hour is not None and local_hour() == nightly_hour and up >= NIGHTLY_MIN_UPTIME:
        return reboot("nightly")
    return None


def main():
    app_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/AppelerMamie")
    state = load_state()
    check_once(app_dir, state)
    save_state(state)


if __name__ == "__main__":
    main()
