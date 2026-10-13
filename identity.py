# ============================================
# FILE: identity.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Loads the identity of the Raspberry from identity.json.

This file must be generated beforehand by setup_identity.py
and contain at least:
{
    "raspberryId": "...",
    "deviceSecret": "..."
}
"""

import json
import sys

import config
from i18n import t


def load_identity():
    """
    Loads identity.json and fills the global variables
    config.RASPBERRY_ID and config.DEVICE_SECRET.

    On error (missing file, invalid JSON, missing fields), the program
    stops (sys.exit).
    """

    if not config.IDENTITY_FILE.exists():
        print(t("identity.fileNotFound", path=config.IDENTITY_FILE))
        print(t("identity.runSetupFirst"))
        sys.exit(1)

    try:
        with open(config.IDENTITY_FILE, 'r') as f:
            identity = json.load(f)

        config.RASPBERRY_ID = identity.get("raspberryId")
        config.DEVICE_SECRET = identity.get("deviceSecret")

        if not config.RASPBERRY_ID or not config.DEVICE_SECRET:
            print(t("identity.invalid"))
            sys.exit(1)

        print(t("identity.loaded", path=config.IDENTITY_FILE))
        print(t("identity.deviceId", device_id=config.RASPBERRY_ID))
        return True

    except json.JSONDecodeError as e:
        print(t("identity.jsonError", error=e))
        sys.exit(1)
    except Exception as e:
        print(t("identity.error", error=e))
        sys.exit(1)
