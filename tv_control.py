# ============================================
# FILE: tv_control.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TV control through CEC (Consumer Electronics Control).

Allows to:
  - turn the TV on and switch to the HDMI input the Raspberry is plugged
    into (config.HDMI_PORT, 3 by default) when a call is accepted,
  - tell the TV that the call is over (tv_return),
  - send the call sound to the TV when it is a TV (call_audio.py).

cec-client commands used:
  - "on 0" : turns the TV on (logical address 0)
  - "as"   : declares the Raspberry as the active source (the TV switches to it)
  - "is"   : declares the Raspberry as an inactive source
  - "-p N" : tells that the Raspberry is plugged into HDMI port N of the TV
              (config.HDMI_PORT)
  - "pow 0": power status of the TV (no answer from a computer monitor)
"""

import re
import subprocess
import threading
import time

import config
from call_audio import route_call_audio

# Power status of a TV that answers HDMI-CEC ("in" = in transition)
TV_POWER_STATES = ("on", "standby", "in")


def switch_hdmi4_background():
    """
    Switches the TV to the HDMI input of the Raspberry (config.HDMI_PORT)
    in the background.
    NB: despite its historical name, the function targets config.HDMI_PORT.
    The CEC command is repeated several times because some TVs do not
    always answer the first attempt.
    Runs in a separate thread so it does not block the caller.
    """
    def switch():
        for _ in range(5):
            subprocess.run(f'echo "as" | cec-client -s -d 1 -p {int(config.HDMI_PORT)}', shell=True)
            time.sleep(1)
        subprocess.run('echo "is" | cec-client -s -d 1', shell=True)
    threading.Thread(target=switch, daemon=True).start()


def tv_answers_cec():
    """True if a TV answers the CEC power request (a computer monitor has no CEC)."""
    try:
        result = subprocess.run('echo "pow 0" | cec-client -s -d 1', shell=True, capture_output=True,
                                text=True, errors="replace", timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    match = re.search(r"power status:\s*(\S+)", getattr(result, "stdout", None) or "")
    return bool(match) and match.group(1) in TV_POWER_STATES


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
    subprocess.run('echo "on 0" | cec-client -s -d 1', shell=True)
    started = time.monotonic()
    tv_present = tv_answers_cec()
    time.sleep(max(0.0, 2 - (time.monotonic() - started)))
    switch_hdmi4_background()
    threading.Thread(target=route_call_audio, args=(tv_present,), daemon=True).start()


def tv_return():
    """Declares the Raspberry as an inactive source (used at the end of a call)."""
    print("📺 Releasing the TV...")
    subprocess.run('echo "is" | cec-client -s -d 1', shell=True)
