# ============================================
# FILE: voice_model.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Speech recognition model of a language (voice_commands.py), downloaded when
the language is changed on the TV (settings page). Same models and SHA-256
as install.sh (VOSK_MODELS, checked by the tests): the file is only used if
its SHA-256 is the expected one, the archive is opened in a temporary folder
of the application and checked before it replaces ~/AppelerMamie/vosk-model.
"""

import hashlib
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import config

MODELS = {
    "fr": ("vosk-model-small-fr-0.22", "cabf6180e177eb9b3a9a9d43a437bd5e549f3a7d09525e5d69a3fed787be12ad"),
    "en": ("vosk-model-small-en-us-0.15", "30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498"),
    "es": ("vosk-model-small-es-0.42", "09b239888f633ef2f0b4e09736e3d9936acfd810bc65d53fad45261762c6511f"),
}
DOWNLOAD_TIMEOUT = 60
MAX_SIZE = 200 * 1024 * 1024


def base_url():
    return os.environ.get("APPELERMAMIE_VOSK_URL", "https://alphacephei.com/vosk/models")


def model_dir():
    return Path(config.BASE_DIR) / "vosk-model"


def installed_name():
    try:
        return (model_dir() / ".name").read_text(encoding="utf-8").strip()
    except OSError:
        return None


def is_installed(lang):
    return lang in MODELS and installed_name() == MODELS[lang][0]


def download(lang, opener=urllib.request.urlopen):
    """
    Installs the model of a language (about 40 MB); True if it is there.
    Never raises: on any problem, the model already there is kept.
    """
    if lang not in MODELS:
        return False
    if is_installed(lang):
        return True
    name, sha = MODELS[lang]
    work = Path(tempfile.mkdtemp(prefix=".vosk-", dir=config.BASE_DIR))
    try:
        archive = work / "model.zip"
        digest = hashlib.sha256()
        size = 0
        with opener(f"{base_url()}/{name}.zip", timeout=DOWNLOAD_TIMEOUT) as response, open(archive, "wb") as f:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_SIZE:
                    raise ValueError("model too big")
                digest.update(chunk)
                f.write(chunk)
        if digest.hexdigest() != sha:
            raise ValueError("unexpected SHA-256")
        with zipfile.ZipFile(archive) as z:
            for member in z.namelist():
                # Only files inside the folder of the model
                target = (work / member).resolve()
                if not str(target).startswith(str((work / name).resolve())):
                    raise ValueError(f"unexpected path in the archive: {member}")
            z.extractall(work)
        if not (work / name / "conf").is_dir() and not (work / name / "am").is_dir():
            raise ValueError("not a model")
        (work / name / ".name").write_text(name + "\n", encoding="utf-8")
        shutil.rmtree(model_dir(), ignore_errors=True)
        os.replace(work / name, model_dir())
        print(f"🗣️ Speech recognition model installed: {name}")
        return True
    except Exception as e:
        print(f"⚠️ Speech recognition model not installed ({e})")
        return False
    finally:
        shutil.rmtree(work, ignore_errors=True)
