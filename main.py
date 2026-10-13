# ============================================
# FILE: main.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TV Control Agent for Raspberry Pi — main entry point.

- Reads the identity from identity.json
- Registers the device on the server
- Receives incoming calls
- Ringtone + TTS announcement (mixed with ffmpeg)
- Accepts the call with a MOUSE CLICK (evdev) OR with the HTML button (sync)
- Controls the TV (CEC)

This file only orchestrates the modules:
  config.py, i18n.py, identity.py, tts_audio.py, tv_control.py, agent.py
"""

import sys
import asyncio

import config
from identity import load_identity
from agent import TVControlAgent
from tts_audio import find_ringing_card, set_max_volume


def main():
    print("""
╔═══════════════════════════════════════╗
║  📺 TV Control Agent v4.0             ║
║  WebSocket + CEC + TTS mix + evdev    ║
║  + HTML <-> Python accept sync        ║
╚═══════════════════════════════════════╝
    """)

    # Loads raspberryId / deviceSecret into config.RASPBERRY_ID / config.DEVICE_SECRET
    load_identity()

    print(f"""
Configuration:
  Identity: {config.IDENTITY_FILE}
  Device ID: {config.RASPBERRY_ID}
  Server: {config.SERVER_URL}
  Language: {config.LANGUAGE}
  Audio cache: {config.CACHE_DIR}
    """)

    # Speaker used for the ringtone: shown at startup (a missing speaker is
    # visible in the logs right away), and its volume set to the maximum.
    # It is searched again at every call.
    card = find_ringing_card()
    if card:
        print(f"🔈 Ringtone speaker: {card['name']} ({card['id']})")
    set_max_volume(card)

    agent = TVControlAgent()

    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        print("\n✅ Clean shutdown")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
