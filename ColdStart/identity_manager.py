# identity_manager.py
"""
Persistent identity of the Raspberry.
Generates and loads raspberryId + deviceSecret securely.
Texts follow LANGUAGE in config.py.
"""

import json
import os
import secrets
import sys
import tempfile
import uuid
from datetime import datetime

# On the Raspberry, every file is in the same folder (~/AppelerMamie).
# In the repository, i18n.py and config.py are in the parent folder.
try:
    import i18n
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import i18n
from device_code import device_code

t = i18n.t


class IdentityManager:
    """Manages the unique and persistent identity of the Raspberry Pi"""

    def __init__(self, filepath=os.path.expanduser("~/AppelerMamie/identity.json")):
        self.filepath = filepath
        self.identity = None

    def load(self):
        """
        Loads the existing identity OR generates it.
        Returns: {"raspberryId": "...", "deviceSecret": "..."}
        """
        if os.path.exists(self.filepath):
            print(t("manager.loading", path=self.filepath))
            self.identity = self._load_from_file()
            print(t("manager.loaded", device_id=self.identity['raspberryId']))
            return self.identity
        else:
            print(t("manager.notFoundGenerating"))
            self.identity = self.generate_and_save()
            print(t("manager.created", device_id=self.identity['raspberryId']))
            return self.identity

    def generate_and_save(self):
        """
        Generates a new identity and saves it atomically.
        Returns: dict with raspberryId + deviceSecret
        """
        identity = {
            "raspberryId": self._generate_raspberry_id(),
            "deviceSecret": secrets.token_hex(32),  # 64 hex characters
            "createdAt": datetime.utcnow().isoformat() + "Z",
            "version": 1
        }
        self._save_atomically(identity)
        return identity

    def _generate_raspberry_id(self):
        """
        Generates a unique raspberryId based on a UUID.
        Format: rpi-{first 8 characters of the UUID}
        Example: rpi-f47ac10b
        """
        unique_id = str(uuid.uuid4())[:8]
        return f"rpi-{unique_id}"

    def _save_atomically(self, data):
        """
        Saves the file ATOMICALLY.
        Protected against power loss during the write.

        Technique: write a temp file → atomic rename
        """
        # Create the folder if it does not exist
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True, mode=0o755)

        # Temp file in the same folder (same filesystem for an atomic rename)
        temp_dir = os.path.dirname(self.filepath)
        temp_fd, temp_path = tempfile.mkstemp(
            dir=temp_dir,
            prefix=".tmp_identity_",
            suffix=".json"
        )

        try:
            # Write the JSON into the temp file
            with os.fdopen(temp_fd, 'w') as f:
                json.dump(data, f, indent=2)

            # STRICT permissions before the rename
            # 600 = owner can read/write, nobody else
            os.chmod(temp_path, 0o600)

            # ATOMIC RENAME: either the old file or the new one exists,
            # never a corrupted file
            os.replace(temp_path, self.filepath)

            print(t("manager.saved", path=self.filepath))
            print(t("manager.permissions"))

        except Exception as e:
            # Remove the temp file on error
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            print(t("manager.saveError", error=e))
            raise

    def _load_from_file(self):
        """Loads and parses the existing identity.json file"""
        try:
            with open(self.filepath, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(t("manager.corrupted", error=e))
            raise
        except FileNotFoundError:
            print(t("manager.fileNotFound", path=self.filepath))
            raise

    def get_raspberry_id(self):
        """Returns the raspberryId (safe to display)"""
        if not self.identity:
            self.load()
        return self.identity.get("raspberryId")

    def get_device_secret(self):
        """Returns the deviceSecret (NEVER print it in logs)"""
        if not self.identity:
            self.load()
        return self.identity.get("deviceSecret")

    def show_identity(self, show_secret=False):
        """Shows the identity (debug)"""
        if not self.identity:
            self.load()

        print("\n" + "=" * 60)
        print(t("manager.title"))
        print("=" * 60)
        print(t("manager.idLabel", value=self.identity['raspberryId']))
        print(t("manager.codeLabel", value=device_code(self.identity['deviceSecret'])))
        print(t("manager.createdLabel", value=self.identity['createdAt']))
        if show_secret:
            print(t("manager.secretLabel", value=self.identity['deviceSecret']))
        else:
            secret = self.identity['deviceSecret']
            masked = secret[:8] + "*" * (len(secret) - 16) + secret[-8:]
            print(t("manager.secretMasked", value=masked))
        print("=" * 60 + "\n")

    def reset(self, backup=True):
        """
        Resets the identity (creates a new one).
        Optional: keeps the old one as .bak
        """
        if backup and os.path.exists(self.filepath):
            backup_path = self.filepath + ".bak"
            print(t("manager.backup", path=backup_path))
            os.replace(self.filepath, backup_path)
        elif os.path.exists(self.filepath):
            os.unlink(self.filepath)

        print(t("manager.generatingNew"))
        self.identity = self.generate_and_save()
        print(t("manager.newIdentity", device_id=self.identity['raspberryId']))
        return self.identity


# ==================== DEBUG CLI ====================

if __name__ == "__main__":
    manager = IdentityManager()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "--show":
            manager.load()
            manager.show_identity(show_secret=False)

        elif cmd == "--show-secret":
            manager.load()
            manager.show_identity(show_secret=True)

        elif cmd == "--reset":
            confirm = input(t("manager.confirmReset"))
            if i18n.is_yes(confirm):
                manager.reset(backup=True)
                manager.show_identity(show_secret=False)
            else:
                print(t("manager.cancelled"))

        else:
            print(t("manager.unknownCommand", command=cmd))
            print(t("manager.usage"))

    else:
        # Default use: load or create
        manager.load()
        manager.show_identity(show_secret=False)
