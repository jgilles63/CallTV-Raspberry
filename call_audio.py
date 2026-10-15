# ============================================
# FILE: call_audio.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Output of the call sound (the voice of the caller, played by Chromium).

Chromium plays the call on the default output of PipeWire. Without help,
PipeWire picks the USB speaker as soon as one is plugged in, and it turns the
HDMI output off when the TV is in standby at boot (it never comes back
when the TV is turned on). So, when a call starts (tv_control.py):

- a TV answers HDMI-CEC and accepts sound (ELD): the HDMI output is turned
  back on if needed and becomes the default output -> the call is heard on
  the TV;
- otherwise (computer monitor: no CEC, TV off or unplugged): the USB
  speaker of the ringtone becomes the default output.

The ringtone and the voice announcement are not concerned: tts_audio.py
plays them directly on the USB speaker.
config.CALL_AUDIO_OUTPUT forces a choice ("hdmi" or "usb"); "auto" by default.

Tools: pw-dump (JSON state of PipeWire) and wpctl (WirePlumber).
"""

import glob
import json
import os
import re
import subprocess
import time

import config

# ELD of the HDMI sound cards: what the screen says about sound
ELD_GLOB = "/proc/asound/card*/eld#*"

# How long the HDMI output is waited for (the TV has just been turned on)
HDMI_ATTEMPTS = 15
HDMI_RETRY_DELAY = 1
COMMAND_TIMEOUT = 10

# Output chosen for the last call ("hdmi", "usb" or None), for the health report
last_route = None


def pipewire_env():
    """Environment of the commands: the agent is a system service, without XDG_RUNTIME_DIR."""
    env = dict(os.environ)
    if not env.get("XDG_RUNTIME_DIR"):
        try:
            uid = os.stat(config.BASE_DIR).st_uid
        except (OSError, AttributeError):
            uid = os.getuid()
        env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
    return env


def run(command):
    """Runs a command, returns its standard output or None if it fails."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, errors="replace",
                                timeout=COMMAND_TIMEOUT, env=pipewire_env())
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def pipewire_objects():
    """Objects of PipeWire (pw-dump), or [] if PipeWire cannot be reached."""
    output = run(["pw-dump"])
    try:
        objects = json.loads(output) if output else []
    except ValueError:
        return []
    return objects if isinstance(objects, list) else []


def props(obj):
    return ((obj or {}).get("info") or {}).get("props") or {}


def params(obj, name):
    return (((obj or {}).get("info") or {}).get("params") or {}).get(name) or []


def objects_of_type(objects, kind):
    return [o for o in objects if o.get("type") == f"PipeWire:Interface:{kind}"]


def device_of_card(objects, card_index):
    """PipeWire device of the ALSA card number card_index, or None."""
    for device in objects_of_type(objects, "Device"):
        if str(props(device).get("api.alsa.card")) == str(card_index):
            return device
    return None


def sinks_of_device(objects, device_id):
    return [n for n in objects_of_type(objects, "Node")
            if props(n).get("media.class") == "Audio/Sink" and str(props(n).get("device.id")) == str(device_id)]


def hdmi_cards_with_sound():
    """
    Numbers of the HDMI sound cards whose screen accepts sound: its ELD has
    a name and at least one audio format. A computer monitor with a headphone
    jack says so too: that is why a CEC answer is required as well.
    """
    cards = []
    for path in sorted(glob.glob(ELD_GLOB)):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        # [ \t] and not \s: an empty name must not take the next line
        name = re.search(r"^monitor_name[ \t]+(\S.*)$", text, re.M)
        sads = re.search(r"^sad_count[ \t]+(\d+)", text, re.M)
        if name and (sads is None or int(sads.group(1)) > 0):
            card = os.path.basename(os.path.dirname(path))[len("card"):]
            if card.isdigit() and card not in cards:
                cards.append(card)
    return cards


def hdmi_profile(device):
    """Output profile of an HDMI device: the available one first, stereo first."""
    profiles = [p for p in params(device, "EnumProfile") if str(p.get("name", "")).startswith("output:hdmi")]
    profiles.sort(key=lambda p: (p.get("available") == "no", p.get("name") != "output:hdmi-stereo"))
    return profiles[0] if profiles else None


def hdmi_sink():
    """
    HDMI output of the screen that accepts sound, turned on if PipeWire left
    it off. Returns the id of its node, or None (not ready yet: try again).
    """
    objects = pipewire_objects()
    for card in hdmi_cards_with_sound():
        device = device_of_card(objects, card)
        if not device:
            continue
        sinks = sinks_of_device(objects, device.get("id"))
        if sinks:
            return sinks[0].get("id")
        profile = hdmi_profile(device)
        if profile is not None:
            print(f"🔊 HDMI output turned on (profile {profile.get('name')})")
            run(["wpctl", "set-profile", str(device.get("id")), str(profile.get("index"))])
    return None


def usb_sink():
    """Output of the USB speaker of the ringtone (same card as tts_audio.py), or None."""
    from tts_audio import find_ringing_card
    card = find_ringing_card()
    if not card:
        return None
    objects = pipewire_objects()
    device = device_of_card(objects, card["index"])
    sinks = sinks_of_device(objects, device.get("id")) if device else []
    return sinks[0].get("id") if sinks else None


def set_default(node_id):
    return run(["wpctl", "set-default", str(node_id)]) is not None


def route_call_audio(tv_present):
    """
    Chooses the output of the call sound (see the top of the file).
    tv_present: a TV answered HDMI-CEC. Runs in a thread: it can wait for the
    HDMI output while the TV turns on. Returns "hdmi", "usb" or None.
    """
    global last_route
    mode = str(getattr(config, "CALL_AUDIO_OUTPUT", "auto") or "auto").lower()
    want_hdmi = mode == "hdmi" or (mode == "auto" and tv_present)

    if want_hdmi:
        for attempt in range(HDMI_ATTEMPTS):
            if attempt:
                time.sleep(HDMI_RETRY_DELAY)
            node = hdmi_sink()
            if node is not None and set_default(node):
                print("🔊 Call sound: TV (HDMI)")
                last_route = "hdmi"
                return last_route
        print("⚠️ HDMI output not available: call sound on the USB speaker")

    node = usb_sink()
    if node is not None and set_default(node):
        reason = "forced" if mode == "usb" else ("no HDMI sound" if want_hdmi else "no TV seen through CEC")
        print(f"🔊 Call sound: USB speaker ({reason})")
        last_route = "usb"
        return last_route
    print("ℹ️ Call sound: default output unchanged (no USB speaker)")
    last_route = None
    return None


def default_sink_name():
    """Description of the current default output of PipeWire, or None."""
    objects = pipewire_objects()
    name = None
    for meta in objects_of_type(objects, "Metadata"):
        # pw-dump gives the props of a metadata object at its top level (no "info")
        meta_props = meta.get("props") or props(meta)
        if meta_props.get("metadata.name") != "default":
            continue
        for entry in meta.get("metadata") or []:
            if entry.get("key") == "default.audio.sink":
                value = entry.get("value")
                name = value.get("name") if isinstance(value, dict) else None
    if not name:
        return None
    for node in objects_of_type(objects, "Node"):
        if props(node).get("node.name") == name:
            return props(node).get("node.description") or name
    return name
