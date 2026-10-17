# ============================================
# FILE: remote_keys.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Keys of the remote control of the TV, received through HDMI-CEC.

Once the Raspberry is declared to the TV as a playback device
(tv_control.ensure_cec_ready), the Linux kernel turns the keys of the remote
control into a keyboard named like the CEC adapter ("vc4-hdmi-0"). This
module finds these keyboards and turns their keys into "up", "down",
"left", "right", "ok" and "back" (seen on a Hisense TV on 17/10/2026: the
arrows, OK = KEY_OK, Back = KEY_EXIT; no digits nor colors).

The keyboards are grabbed: only the agent reads them (it sends the keys to
the TV page through the server), Chromium does not get them twice.
"""

import asyncio
import glob
import os
import time

from evdev import InputDevice, ecodes, list_devices

# Kernel key -> key of the project
KEYS = {
    "KEY_UP": "up",
    "KEY_DOWN": "down",
    "KEY_LEFT": "left",
    "KEY_RIGHT": "right",
    "KEY_OK": "ok",
    "KEY_SELECT": "ok",
    "KEY_ENTER": "ok",
    "KEY_EXIT": "back",
    "KEY_BACK": "back",
    "KEY_ESC": "back",
}
# Keys repeated while held down (the others: once per press)
REPEATED = {"up", "down", "left", "right"}
# At most one repeat every 0.25 s: the server closes a connection that sends
# more than 100 messages in 10 s (server-limits.js)
REPEAT_INTERVAL = 0.25

# Remote controls through CEC: rc devices of the kernel with the "cec" protocol
RC_DIR = "/sys/class/rc"
# Searched again after this delay when none is found (or when it is lost)
RETRY_DELAY = 30


def cec_keyboard_names():
    """Names of the keyboards made by the kernel for the CEC adapters."""
    names = set()
    for rc in glob.glob(os.path.join(RC_DIR, "rc*")):
        try:
            with open(os.path.join(rc, "protocols"), encoding="utf-8") as f:
                if "cec" not in f.read():
                    continue
        except OSError:
            continue
        for name_file in glob.glob(os.path.join(rc, "input*", "name")):
            try:
                with open(name_file, encoding="utf-8") as f:
                    names.add(f.read().strip())
            except OSError:
                pass
    return names


def find_keyboards():
    """Input devices of the CEC remote controls (possibly none)."""
    names = cec_keyboard_names()
    keyboards = []
    for path in sorted(list_devices()):
        try:
            device = InputDevice(path)
        except OSError:
            continue
        if device.name in names:
            keyboards.append(device)
        else:
            device.close()
    return keyboards


def key_of(event):
    """Key of the project for an input event, or None (released key, other key)."""
    if event.type != ecodes.EV_KEY:
        return None
    names = ecodes.KEY.get(event.code)
    for name in names if isinstance(names, list) else [names]:
        key = KEYS.get(name)
        if key and (event.value == 1 or (event.value == 2 and key in REPEATED)):
            return key
    return None


async def read_keyboard(device, on_key):
    """Reads one keyboard until it disappears; on_key(key) is awaited for each key."""
    try:
        device.grab()
    except OSError as e:
        print(f"⚠️ Remote control {device.name}: not grabbed ({e}), Chromium may get the keys too")
    print(f"📺 Remote control of the TV listened to ({device.name}, {device.path})")
    last_repeat = 0.0
    try:
        async for event in device.async_read_loop():
            key = key_of(event)
            if not key:
                continue
            if event.value == 2:
                now = time.monotonic()
                if now - last_repeat < REPEAT_INTERVAL:
                    continue
                last_repeat = now
            await on_key(key)
    except OSError as e:
        print(f"⚠️ Remote control {device.name} lost ({e})")
    finally:
        try:
            device.close()
        except Exception:
            pass


async def listen(on_key, retry_delay=RETRY_DELAY):
    """
    Listens to the remote controls of the TV for the whole life of the agent:
    searched again after retry_delay seconds when none is found or lost.
    """
    notice_shown = False
    while True:
        keyboards = find_keyboards()
        if keyboards:
            notice_shown = False
            await asyncio.gather(*(read_keyboard(device, on_key) for device in keyboards))
        elif not notice_shown:
            print("ℹ️ No CEC remote control found (TV without CEC?), searching again later")
            notice_shown = True
        await asyncio.sleep(retry_delay)
