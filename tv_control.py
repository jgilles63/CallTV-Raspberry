# ============================================
# FILE: tv_control.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TV control through CEC (Consumer Electronics Control), with cec-ctl (the CEC
tool of the Linux kernel, package v4l-utils).

Allows to:
  - turn the TV on and switch to the HDMI input of the Raspberry when a call
    is accepted,
  - tell the TV that the call is over (tv_return),
  - send the call sound to the TV when it is a TV (call_audio.py),
  - receive the keys of the remote control of the TV: the Raspberry stays
    declared as a "playback" device (ensure_cec_ready), so the kernel turns
    the keys into a keyboard (agent.py reads it).

cec-client is no longer used: when it ends, it clears the CEC configuration
of the Raspberry (seen on 17/10/2026), and the TV would stop sending the keys.

cec-ctl commands used (-d <adapter>):
  - "--playback --osd-name AppelerMamie": declares the Raspberry (once,
    kept by the kernel)
  - "--to 0 --image-view-on": turns the TV on
  - "--to 15 --active-source phys-addr=A.B.C.D": the Raspberry becomes the
    active source (the TV switches to its input)
  - "--to 0 --inactive-source phys-addr=A.B.C.D": end of the call
  - "--to 0 --give-device-power-status": power status of the TV (no answer
    from a computer monitor)
The physical address (3.0.0.0 = input 3) is given by the TV; config.HDMI_PORT
is used only when the TV does not give it.
"""

import glob
import re
import subprocess
import threading
import time

import config
from call_audio import route_call_audio

CEC_TOOL = "cec-ctl"
OSD_NAME = "AppelerMamie"
TV = "0"
BROADCAST = "15"
COMMAND_TIMEOUT = 10
# Physical address when the TV gives none (HDMI not connected or no CEC)
UNKNOWN_ADDRESS = "f.f.f.f"

# "pwr-state: in transition standby to on (0x02)" -> state of the TV
POWER_STATES = {
    "on": "on",
    "standby": "standby",
    "in transition standby to on": "to-on",
    "in transition on to standby": "to-standby",
}

# Adapter already declared once by this program (message shown once)
_declared = set()


def cec_ctl(adapter, *args):
    """Runs cec-ctl on an adapter; returns its output, or None if it fails to run."""
    try:
        result = subprocess.run([CEC_TOOL, "-d", adapter, *args], capture_output=True, text=True,
                                errors="replace", timeout=COMMAND_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    return (result.stdout or "") + (result.stderr or "")


def adapter_info(adapter):
    """Physical address and logical address mask of an adapter (None if unreadable)."""
    output = cec_ctl(adapter)
    if output is None:
        return None
    physical = re.search(r"Physical Address\s*:\s*([0-9a-f]\.[0-9a-f]\.[0-9a-f]\.[0-9a-f])", output)
    mask = re.search(r"Logical Address Mask\s*:\s*0x([0-9a-f]+)", output)
    name = re.search(r"Adapter Name\s*:\s*(\S+)", output)
    return {
        "physical": physical.group(1) if physical else UNKNOWN_ADDRESS,
        "declared": bool(mask and int(mask.group(1), 16)),
        "name": name.group(1) if name else None,
    }


def find_adapter():
    """
    CEC adapter of the HDMI output connected to the TV (the one with a
    physical address), else the first one. Returns (adapter, info) or (None, None).
    """
    found = []
    for adapter in sorted(glob.glob("/dev/cec*")):
        info = adapter_info(adapter)
        if info is not None:
            found.append((adapter, info))
    for adapter, info in found:
        if info["physical"] != UNKNOWN_ADDRESS:
            return adapter, info
    return found[0] if found else (None, None)


def physical_address(info):
    """Physical address of the Raspberry: given by the TV, else from config.HDMI_PORT."""
    if info and info["physical"] != UNKNOWN_ADDRESS:
        return info["physical"]
    try:
        port = int(getattr(config, "HDMI_PORT", 3))
    except (TypeError, ValueError):
        port = 3
    return f"{port}.0.0.0"


def ensure_cec_ready():
    """
    Declares the Raspberry as a playback device if it is not (anymore): the
    TV then sends it the keys of its remote control. Cheap when already
    declared. Returns (adapter, physical address), adapter None without CEC.
    """
    adapter, info = find_adapter()
    if adapter is None:
        return None, physical_address(None)
    if not info["declared"]:
        cec_ctl(adapter, "--playback", "--osd-name", OSD_NAME)
        if adapter not in _declared:
            print(f"📺 CEC: Raspberry declared to the TV ({adapter}, {info['physical']})")
            _declared.add(adapter)
    return adapter, physical_address(info)


def tv_power(adapter=None):
    """Power status of the TV: "on", "standby", "to-on", "to-standby", or None (no answer)."""
    if adapter is None:
        adapter, _ = ensure_cec_ready()
        if adapter is None:
            return None
    output = cec_ctl(adapter, "--to", TV, "--give-device-power-status") or ""
    match = re.search(r"pwr-state:\s*([a-z][a-z ]*?)\s*\(", output)
    return POWER_STATES.get(match.group(1)) if match else None


def tv_answers_cec(adapter=None):
    """True if a TV answers the CEC power request (a computer monitor has no CEC)."""
    return tv_power(adapter) is not None


def switch_hdmi4_background(adapter=None, address=None):
    """
    Switches the TV to the HDMI input of the Raspberry, in the background.
    NB: despite its historical name, the function targets the input of the
    Raspberry (physical address given by the TV, else config.HDMI_PORT).
    The command is repeated because some TVs do not always answer the first
    attempt. Runs in a separate thread so it does not block the caller.
    """
    if adapter is None:
        adapter, address = ensure_cec_ready()
    if adapter is None:
        return

    def switch():
        for _ in range(5):
            cec_ctl(adapter, "--to", BROADCAST, "--active-source", f"phys-addr={address}")
            time.sleep(1)
    threading.Thread(target=switch, daemon=True).start()


def tv_on_and_accept():
    """
    Full call-accept sequence on the TV side:
      1. Turn the TV on
      2. Ask its power status (is it a TV?) while it wakes up (2 s at least)
      3. Switch to the HDMI input of the Raspberry (in the background,
         see switch_hdmi4_background)
      4. Choose the output of the call sound (in the background: TV if it
         answered CEC and accepts sound, USB speaker otherwise)
    """
    print("📺 Turning the TV on (HDMI)...")
    adapter, address = ensure_cec_ready()
    started = time.monotonic()
    tv_present = False
    if adapter is not None:
        cec_ctl(adapter, "--to", TV, "--image-view-on")
        tv_present = tv_answers_cec(adapter)
    time.sleep(max(0.0, 2 - (time.monotonic() - started)))
    switch_hdmi4_background(adapter, address)
    threading.Thread(target=route_call_audio, args=(tv_present,), daemon=True).start()


def tv_return():
    """Declares the Raspberry as an inactive source (used at the end of a call)."""
    print("📺 Releasing the TV...")
    adapter, address = ensure_cec_ready()
    if adapter is not None:
        cec_ctl(adapter, "--to", TV, "--inactive-source", f"phys-addr={address}")
