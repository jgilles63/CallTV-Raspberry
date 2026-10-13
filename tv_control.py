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
  - tell the TV that the call is over (tv_return).

cec-client commands used:
  - "on 0" : turns the TV on (logical address 0)
  - "as"   : declares the Raspberry as the active source (the TV switches to it)
  - "is"   : declares the Raspberry as an inactive source
  - "-p N" : tells that the Raspberry is plugged into HDMI port N of the TV
              (config.HDMI_PORT)
"""

import subprocess
import threading
import time

import config


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


def tv_on_and_accept():
    """
    Full call-accept sequence on the TV side:
      1. Turn the TV on
      2. Wait 2 s (time for the TV to wake up)
      3. Switch to the HDMI input of the Raspberry (in the background,
         see switch_hdmi4_background)
    """
    print("📺 Turning the TV on (HDMI)...")
    subprocess.run('echo "on 0" | cec-client -s -d 1', shell=True)
    time.sleep(2)
    switch_hdmi4_background()


def tv_return():
    """Declares the Raspberry as an inactive source (used at the end of a call)."""
    print("📺 Releasing the TV...")
    subprocess.run('echo "is" | cec-client -s -d 1', shell=True)
