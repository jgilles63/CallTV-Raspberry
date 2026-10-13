# ============================================
# FILE: device_code.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verification code of the Raspberry, e.g. "K7QM-2XPA-9DFR".

It is derived from the device secret (SHA-256), so it proves which
Raspberry is asking for an authorization, without revealing the secret.
The server administrator authorizes the identifier AND this code
(node admin.js add <id> <code>): another machine using the same
identifier has another code and stays refused.

Same computation on the server: Server/server-device-code.js.
"""

import hashlib

# Crockford base32: no I, L, O, U (easy to read and to dictate)
CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CODE_PREFIX = "appelermamie-device-code:"


def device_code(secret):
    """12 characters (60 bits of SHA-256), grouped by 4."""
    digest = hashlib.sha256((CODE_PREFIX + secret).encode("utf-8")).digest()
    bits = int.from_bytes(digest[:8], "big") >> 4
    chars = "".join(CODE_ALPHABET[(bits >> (5 * i)) & 31] for i in range(11, -1, -1))
    return f"{chars[:4]}-{chars[4:8]}-{chars[8:]}"
