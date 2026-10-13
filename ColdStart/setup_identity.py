#!/usr/bin/env python3
# setup_identity.py
"""
Setup script to run ONCE when deploying the Raspberry.
python3 setup_identity.py

Generates the identity of the Raspberry and a QR code in a .txt file
for easy scanning. Texts follow LANGUAGE in config.py.
"""

import os
import sys

import qrcode

from identity_manager import IdentityManager, device_code, i18n


def generate_qr_code_text(data):
    """
    Generates a QR code as ASCII art (text format).

    Returns: string containing the ASCII QR code
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr.add_data(data)
    qr.make(fit=True)

    # Build the ASCII image
    ascii_qr = ""
    for row in qr.modules:
        for module in row:
            ascii_qr += "██" if module else "  "
        ascii_qr += "\n"

    return ascii_qr


def save_qr_code(raspberry_id, code, output_dir=os.path.expanduser("~/AppelerMamie")):
    """
    Saves the QR code in a .txt file.

    The QR code contains: rpi-xxxxx
    """
    os.makedirs(output_dir, exist_ok=True)

    content = i18n.t(
        "setup.qrFile",
        qr=generate_qr_code_text(raspberry_id),
        device_id=raspberry_id,
        code=code,
    )

    output_file = os.path.join(output_dir, "setup_qr_code.txt")
    descriptor = os.open(output_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(content)

    print(i18n.t("setup.qrSaved", path=output_file))

    return output_file


def main():
    print("\n" + "=" * 70)
    print(i18n.t("setup.title"))
    print("=" * 70 + "\n")

    filepath = os.path.expanduser("~/AppelerMamie/identity.json")
    manager = IdentityManager(filepath)

    if os.path.exists(filepath):
        # The identity already exists
        print(i18n.t("setup.exists"))
        response = input(i18n.t("setup.askReset"))
        if i18n.is_yes(response):
            manager.reset(backup=True)
            manager.show_identity(show_secret=False)

            save_qr_code(manager.identity['raspberryId'], device_code(manager.identity['deviceSecret']))

            print(i18n.t("setup.resetDone"))
            print(i18n.t("setup.backupKept"))
        else:
            print(i18n.t("setup.cancelled"))
            sys.exit(0)
    else:
        # First setup
        print(i18n.t("setup.generatingFirst"))
        manager.load()
        manager.show_identity(show_secret=False)

        save_qr_code(manager.identity['raspberryId'], device_code(manager.identity['deviceSecret']))

        print(i18n.t("setup.done"))
        print(i18n.t("setup.file", path=filepath))
        print(i18n.t("setup.permissions"))
        print(i18n.t("setup.permanent"))

    print("=" * 70)
    print(i18n.t("setup.nextSteps"))
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
