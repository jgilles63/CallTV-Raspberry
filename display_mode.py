# ============================================
# FILE: display_mode.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Screen resolution of the TV: 1920 x 1080 instead of 4K.

A 4K TV gives its 4K mode (3840 x 2160, often at 30 Hz) as preferred: the
Raspberry Pi 4 then draws 4 times more pixels, and a video call stutters
(seen on 17/10/2026: processor at 80-94 %, then slowed down by the heat).
For a video call, 1920 x 1080 is enough and much lighter.

ensure_screen_mode(): an output wider than 1920 pixels is set to 1920 x 1080
at the highest refresh rate up to 60 Hz that the TV offers (60 Hz: a 25 or
30 images/s video plays evenly). A screen of 1920 pixels or less is never
changed. Called when Chromium starts (launch_chromium.sh) and every 30 s by
the agent (the TV may give its 4K mode again when it is plugged back in).
config.SCREEN_MODE = None leaves the screen as the TV wants it.

second_screen(): size of a second screen plugged on the second micro-HDMI
(HDMI-A-2; the TV is always HDMI-A-1, the one next to the power socket), or
None. With one, the touch page of the TV (ecran.html) opens on it
(launch_chromium.sh). config.SECOND_SCREEN = False: never.

Tool: wlr-randr (desktop of Raspberry Pi OS, labwc / Wayland). Runs as the
user of the Raspberry; the Wayland socket is found in /run/user/<uid>/.
"""

import glob
import os
import re
import subprocess

import config

MAX_WIDTH = 1920
TARGET = (1920, 1080)
# Highest refresh rate chosen (60 Hz, or 59.94 Hz)
MAX_REFRESH = 60.5
COMMAND_TIMEOUT = 10
# The TV, and the second screen (touch page)
TV_OUTPUT = "HDMI-A-1"
SECOND_OUTPUT = "HDMI-A-2"

MODE_LINE = re.compile(r"^\s+(\d+)x(\d+) px, ([\d.]+) Hz(.*)$")


def wayland_env():
    """Environment of wlr-randr: the agent and Chromium are system services."""
    env = dict(os.environ)
    if not env.get("XDG_RUNTIME_DIR"):
        try:
            uid = os.stat(config.BASE_DIR).st_uid
        except (OSError, AttributeError):
            uid = os.getuid()
        env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
    if not env.get("WAYLAND_DISPLAY"):
        sockets = sorted(p for p in glob.glob(os.path.join(env["XDG_RUNTIME_DIR"], "wayland-*")) if not p.endswith(".lock"))
        env["WAYLAND_DISPLAY"] = os.path.basename(sockets[0]) if sockets else "wayland-0"
    return env


def run(command):
    """Runs a command, returns its output or None if it fails."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, errors="replace",
                                timeout=COMMAND_TIMEOUT, env=wayland_env())
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def parse_outputs(text):
    """
    Outputs of `wlr-randr`: [{name, enabled, current: (w, h, hz) or None,
    modes: [(w, h, hz), ...]}].
    """
    outputs = []
    for line in (text or "").splitlines():
        if line and not line[0].isspace():
            outputs.append({"name": line.split()[0], "enabled": True, "current": None, "modes": []})
            continue
        if not outputs:
            continue
        output = outputs[-1]
        if line.strip().startswith("Enabled:"):
            output["enabled"] = line.split(":", 1)[1].strip() == "yes"
        mode = MODE_LINE.match(line)
        if mode:
            width, height, refresh = int(mode.group(1)), int(mode.group(2)), float(mode.group(3))
            output["modes"].append((width, height, refresh))
            if "current" in mode.group(4):
                output["current"] = (width, height, refresh)
    return outputs


def best_mode(modes):
    """1920 x 1080 at the highest refresh rate up to 60 Hz, or None."""
    candidates = [m for m in modes if (m[0], m[1]) == TARGET and m[2] <= MAX_REFRESH]
    return max(candidates, key=lambda m: m[2]) if candidates else None


def current_mode():
    """Current mode of the enabled outputs: [(name, (w, h, hz))]."""
    return [(o["name"], o["current"]) for o in parse_outputs(run(["wlr-randr"])) if o["enabled"] and o["current"]]


def second_screen():
    """
    (width, height) of the screen on HDMI-A-2 when the TV is on HDMI-A-1
    too, or None. A TV plugged alone on HDMI-A-2 is one screen: no change.
    """
    if getattr(config, "SECOND_SCREEN", "auto") is False:
        return None
    shown = {o["name"]: o["current"] for o in parse_outputs(run(["wlr-randr"])) if o["enabled"] and o["current"]}
    if TV_OUTPUT not in shown or SECOND_OUTPUT not in shown:
        return None
    width, height, _refresh = shown[SECOND_OUTPUT]
    return (width, height)


def ensure_screen_mode():
    """Sets 1920 x 1080 on the outputs wider than 1920 pixels. Returns [(name, mode)] changed."""
    if getattr(config, "SCREEN_MODE", "1080p") != "1080p":
        return []
    changed = []
    for output in parse_outputs(run(["wlr-randr"])):
        current = output["current"]
        if not output["enabled"] or not current or current[0] <= MAX_WIDTH:
            continue
        mode = best_mode(output["modes"])
        if mode is None:
            continue
        width, height, refresh = mode
        if run(["wlr-randr", "--output", output["name"], "--mode", f"{width}x{height}@{refresh:.6f}Hz"]) is not None:
            print(f"🖥️ Screen {output['name']}: {current[0]}x{current[1]} -> {width}x{height} at {refresh:g} Hz")
            changed.append((output["name"], mode))
    return changed


def main(argv):
    """
    No argument: 4K TV set to 1920 x 1080 (start of Chromium).
    --second: prints the size of the second screen ("1024x600") and exits 0,
    or prints nothing and exits 1 (launch_chromium.sh opens the touch page).
    """
    if "--second" in argv:
        size = second_screen()
        if size is None:
            return 1
        print(f"{size[0]}x{size[1]}")
        return 0
    ensure_screen_mode()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
