#!/bin/bash
# ============================================
# FILE: install.sh
# ============================================
# Installs (or updates) the Raspberry receiver in one command.
#
# Before: Raspberry Pi OS **with desktop** written with Raspberry Pi Imager
# (user, Wi-Fi and SSH set in the Imager settings), then the project downloaded
# on the Raspberry: git clone https://github.com/jgilles63/CallTV-Raspberry.git
# ~/AppelerMamie-src (or this folder, Raspberry_receiver, copied there).
#
# Usage, as the Raspberry user (NOT with sudo):
#   bash install.sh             # asks the language (fr / en / es)
#   bash install.sh --lang es   # without the question
#   bash install.sh --lang es --greeting abuela   # greeting of the announcement
#                               # ("" = none), asked at the first installation
#
# It can be run again at any time to update a Raspberry: the identity
# (identity.json) and the settings of config.py are kept.
# Messages follow the chosen language (texts in i18n.py, "install.*" keys).

set -Eeuo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/AppelerMamie"
LOG_FILE="$HOME/appelermamie-install.log"
PYTHON=python3
export PYTHONDONTWRITEBYTECODE=1

# System packages: audio conversion/playback, TV control (CEC), Python
# virtual environment (+ build tools for evdev). The browser (chromium) is
# installed apart: see the "packages" step.
APT_PACKAGES=(ffmpeg alsa-utils cec-utils python3-venv python3-dev build-essential)

# Python packages of the agent (versions tested on Raspberry Pi OS 13 "trixie")
PIP_PACKAGES=("websockets>=13,<18" "evdev>=1.6,<3" "gTTS>=2.5,<3" "qrcode>=7,<9")

TOTAL_STEPS=10
STEP=0
STEP_NAME=""
LANG_CHOICE=""
GREETING_CHOICE=""
GREETING_SET=""

# ---------------------------------------------------------
# Options
# ---------------------------------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    --lang) LANG_CHOICE="${2:-}"; shift; [ $# -gt 0 ] && shift ;;
    --lang=*) LANG_CHOICE="${1#--lang=}"; shift ;;
    --greeting) GREETING_CHOICE="${2-}"; GREETING_SET=1; shift; [ $# -gt 0 ] && shift ;;
    --greeting=*) GREETING_CHOICE="${1#--greeting=}"; GREETING_SET=1; shift ;;
    -h|--help) sed -n '5,20p' "$0"; exit 0 ;;
    *) echo "❌ Unknown option: $1 (see --help)" >&2; exit 1 ;;
  esac
done

# The project files must be next to this script (no translation available otherwise)
for f in main.py config.py i18n.py ColdStart/setup_identity.py ColdStart/tv-control.service ColdStart/chromium-autolaunch.service; do
  if [ ! -f "$SRC_DIR/$f" ]; then
    echo "❌ $f ?" >&2
    echo "   Lancez ce script depuis le dossier du projet (clone de CallTV-Raspberry ou Raspberry_receiver)." >&2
    echo "   Run this script from the project folder (clone of CallTV-Raspberry or Raspberry_receiver)." >&2
    echo "   Ejecuta este script desde la carpeta del proyecto (clon de CallTV-Raspberry o Raspberry_receiver)." >&2
    exit 1
  fi
done

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

# i18n.py only needs config.LANGUAGE: a minimal config is given to it, so that
# loading the real config.py (which creates the cache folder) is avoided.
I18N_SETUP='import os, sys, types
sys.modules["config"] = types.SimpleNamespace(LANGUAGE=os.environ.get("AM_LANG") or "fr")
import i18n'

# Translated message: msg <key> [name=value ...]
msg() {
  (cd "$SRC_DIR" && AM_LANG="$LANG_CHOICE" "$PYTHON" -c "$I18N_SETUP
key, *pairs = sys.argv[1:]
print(i18n.t(key, **dict(pair.split('=', 1) for pair in pairs)))" "$@")
}

# True if the answer means "yes" in the chosen language (o/y/s...)
is_yes() {
  (cd "$SRC_DIR" && "$PYTHON" -c "$I18N_SETUP
sys.exit(0 if i18n.is_yes(sys.argv[1]) else 1)" "$1")
}

ask() {
  local answer=""
  read -r -p "$(msg "$1")" answer || true
  is_yes "$answer"
}

step() {
  STEP=$((STEP + 1))
  STEP_NAME="$(msg "$@")"
  echo
  echo "━━━ [$STEP/$TOTAL_STEPS] $STEP_NAME"
}

on_error() {
  # Only once, in the main script (not again in each sub-shell)
  [ "$BASH_SUBSHELL" -eq 0 ] || return 0
  echo
  msg install.failed step="$STEP_NAME" log="$LOG_FILE" >&2 || true
}
trap on_error ERR

# ---------------------------------------------------------
# Language (asked first: all the following messages use it)
# ---------------------------------------------------------
if [ -z "$LANG_CHOICE" ]; then
  default_lang=""
  if [ -f "$APP_DIR/config.py" ]; then
    default_lang="$(sed -n 's/^LANGUAGE *= *"\([a-z][a-z]\)".*/\1/p' "$APP_DIR/config.py" | head -1)"
  fi
  default_lang="${default_lang:-fr}"
  read -r -p "Langue / Language / Idioma (fr, en, es) [$default_lang] : " LANG_CHOICE || true
  LANG_CHOICE="${LANG_CHOICE:-$default_lang}"
fi
case "$LANG_CHOICE" in
  fr|en|es) ;;
  *) echo "❌ Langue / Language / Idioma : fr, en, es" >&2; exit 1 ;;
esac

if [ "$(id -u)" -eq 0 ]; then
  msg install.noRoot >&2
  exit 1
fi

# Greeting of the voice announcement ("Hey grandma, ..."): asked at the first
# installation only (an update keeps the value of config.py)
if [ -z "$GREETING_SET" ] && [ ! -f "$APP_DIR/config.py" ]; then
  # (question printed apart: read -p shows nothing when the answers come from a pipe)
  printf '%s' "$(msg install.askGreeting)"
  read -r GREETING_CHOICE || true
  echo
  GREETING_SET=1
fi

# Everything is also written to the log file
exec > >(tee -a "$LOG_FILE") 2>&1
echo
echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="
msg install.title

# ---------------------------------------------------------
# 1. Checks
# ---------------------------------------------------------
step install.checks

if ! getent hosts deb.debian.org >/dev/null; then
  msg install.noInternet
  exit 1
fi

if [ ! -x /usr/sbin/lightdm ] && ! command -v labwc >/dev/null && ! command -v startx >/dev/null; then
  msg install.noDesktop
  if ! ask install.askContinue; then
    msg install.stopped
    exit 1
  fi
fi

msg install.sudo
sudo -v
# Keep the sudo rights during the whole installation
( while kill -0 "$$" 2>/dev/null; do sudo -n true; sleep 50; done ) 2>/dev/null &

# ---------------------------------------------------------
# 2. System packages
# ---------------------------------------------------------
step install.packages
sudo apt-get update -q
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${APT_PACKAGES[@]}"
# Chromium is installed if missing, but never upgraded by this script: a new
# version once stopped the camera and the microphone of the calls (11/10/2026).
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-upgrade chromium

# ---------------------------------------------------------
# 3. Project files, copied flat into ~/AppelerMamie
# ---------------------------------------------------------
step install.files dir="$APP_DIR"
mkdir -p "$APP_DIR"

# Files created by another user (e.g. with sudo during a manual install)
# cannot be replaced: they are given back to the Raspberry user.
if [ -n "$(find "$APP_DIR" \( ! -user "$(id -u)" -o ! -writable \) -print -quit 2>/dev/null)" ]; then
  sudo chown -R "$USER:" "$APP_DIR"
  sudo chmod -R u+w "$APP_DIR"
fi

old_config=""
if [ -f "$APP_DIR/config.py" ]; then
  old_config="$APP_DIR/config.py.bak-$(date +%Y%m%d-%H%M%S)"
  cp -p "$APP_DIR/config.py" "$old_config"
fi

# config.py is handled below: it is only replaced once the previous values
# have been put back (an interrupted run never leaves the default settings)
for f in "$SRC_DIR"/*.py "$SRC_DIR"/*.sh "$SRC_DIR"/*.mp3 \
         "$SRC_DIR"/ColdStart/*.py "$SRC_DIR"/ColdStart/*.sh "$SRC_DIR"/HomeAssistant/*.sh; do
  [ -f "$f" ] || continue
  [ "$(basename "$f")" = config.py ] && continue
  dest="$APP_DIR/$(basename "$f")"
  # The folder may already be ~/AppelerMamie itself
  [ "$f" -ef "$dest" ] || cp -p "$f" "$dest"
done

# Files copied from Windows may have Windows line endings
sed -i 's/\r$//' "$APP_DIR"/*.py "$APP_DIR"/*.sh
chmod +x "$APP_DIR"/*.sh

# New config.py = the one of the project + the values of the previous one +
# the chosen language and greeting, prepared in a temporary file then moved in
# one go. A MOUSE_DEVICE such as /dev/input/event4 changes with the USB port:
# it is replaced by the automatic detection. An older config.py without
# GREETING_NAME keeps the announcement it had ("Hey grandma, ...").
new_config="$APP_DIR/.config.py.new"
sed 's/\r$//' "$SRC_DIR/config.py" > "$new_config"
config_notes="$("$PYTHON" - "$new_config" "$old_config" "$LANG_CHOICE" "$GREETING_SET" "$GREETING_CHOICE" <<'PY'
import re
import sys

new_path, old_path, lang, greeting_set, greeting = sys.argv[1:6]
KEPT = ("SERVER_URL", "UNAUTHORIZED_RETRY_DELAY", "MOUSE_DEVICE", "MOUSE_RETRY_DELAY",
        "HDMI_PORT", "AUDIO_DEVICE", "RINGTONE_PATH", "CALL_DURATION", "MAX_CACHED_CALLS",
        "MAX_CALLER_NAME_LENGTH", "VOICE_VOLUME", "RINGTONE_VOLUME", "NIGHTLY_REBOOT_HOUR",
        "GREETING_NAME")
# Greeting of the announcement before GREETING_NAME existed
FORMER_GREETING = {"fr": "mamie", "en": "grandma", "es": "abuela"}


def setting(key, text):
    match = re.search(rf"^{key} *=.*$", text, re.M)
    return match.group(0) if match else None


with open(new_path, encoding="utf-8") as f:
    new = f.read()

if old_path:
    with open(old_path, encoding="utf-8") as f:
        old = f.read()
    for key in KEPT:
        old_line, new_line = setting(key, old), setting(key, new)
        if not old_line or not new_line or old_line == new_line:
            continue
        if key == "MOUSE_DEVICE" and re.search(r'"/dev/input/event\d+"', old_line):
            print("mouse=" + old_line.split("=", 1)[1].strip())
            continue
        new = new.replace(new_line, old_line, 1)


def set_greeting(value):
    global new
    clean = "".join(c for c in value.strip()[:30] if c.isalnum() or c in " -'").strip()
    line = f'GREETING_NAME = "{clean}"' if clean else "GREETING_NAME = None"
    new = re.sub(r"^GREETING_NAME *=.*$", line, new, count=1, flags=re.M)


if greeting_set:
    set_greeting(greeting)
    print("greeting=set")
elif old_path and not setting("GREETING_NAME", old):
    set_greeting(FORMER_GREETING[lang])
    print("greeting=kept")

new = re.sub(r"^LANGUAGE *=.*$", f'LANGUAGE = "{lang}"', new, count=1, flags=re.M)

with open(new_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(new)
PY
)"
mv "$new_config" "$APP_DIR/config.py"
if [ -n "$old_config" ]; then
  msg install.configKept backup="$old_config"
fi
mouse_reset="$(sed -n 's/^mouse=//p' <<< "$config_notes")"
if [ -n "$mouse_reset" ]; then
  msg install.mouseReset old="$mouse_reset"
fi
greeting_note="$(sed -n 's/^greeting=//p' <<< "$config_notes")"
if [ -n "$greeting_note" ]; then
  greeting="$(sed -n 's/^GREETING_NAME *= *"\(.*\)".*/\1/p' "$APP_DIR/config.py" | head -1)"
  if [ -n "$greeting" ]; then
    phrase="$(msg tts.phrase name=Paul greeting="$greeting")"
  else
    phrase="$(msg tts.phraseNoGreeting name=Paul)"
  fi
  if [ "$greeting_note" = kept ]; then
    msg install.greetingKept phrase="$phrase"
  else
    msg install.greeting phrase="$phrase"
  fi
fi

# ---------------------------------------------------------
# 4. Python environment
# ---------------------------------------------------------
step install.python
if [ ! -x "$APP_DIR/venv/bin/python3" ]; then
  "$PYTHON" -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install -q "${PIP_PACKAGES[@]}"

# ---------------------------------------------------------
# 5. Ringtone: aplay plays WAV files
# ---------------------------------------------------------
step install.ringtone
# Every .mp3 of the folder: ringtone.mp3 of the project, and a ringtone of
# one's own copied there (see RINGTONE_PATH in config.py)
for mp3 in "$APP_DIR"/*.mp3; do
  [ -f "$mp3" ] || continue
  wav="${mp3%.mp3}.wav"
  if [ ! -f "$wav" ] || [ "$mp3" -nt "$wav" ]; then
    ffmpeg -y -loglevel error -i "$mp3" "$wav"
  fi
done

# ---------------------------------------------------------
# 6. User rights: mouse (input), TV CEC (video), sound (audio)
# ---------------------------------------------------------
step install.groups
groups_to_add=""
for g in input video audio render; do
  if getent group "$g" >/dev/null; then
    groups_to_add="${groups_to_add:+$groups_to_add,}$g"
  fi
done
sudo usermod -aG "$groups_to_add" "$USER"

# ---------------------------------------------------------
# 7. Identity of the Raspberry (kept if it already exists)
# ---------------------------------------------------------
step install.identity
identity_file="$APP_DIR/identity.json"
read_device_id() {
  "$PYTHON" -c 'import json, sys; print(json.load(open(sys.argv[1]))["raspberryId"])' "$identity_file"
}
if [ -f "$identity_file" ]; then
  msg install.identityKept device_id="$(read_device_id)"
else
  (cd "$APP_DIR" && "$APP_DIR/venv/bin/python3" setup_identity.py)
fi
device_id="$(read_device_id)"
# The identity holds the device secret: readable by the Raspberry user only
# (identities created by older versions could be readable by everyone)
chmod 600 "$identity_file"
# Verification code, given to the administrator with the identifier
device_code="$(cd "$APP_DIR" && "$PYTHON" -c \
  'import json, sys; from device_code import device_code; print(device_code(json.load(open(sys.argv[1]))["deviceSecret"]))' \
  "$identity_file")"

# ---------------------------------------------------------
# 8. Services: agent + Chromium on the TV, started at boot
# ---------------------------------------------------------
step install.services
for service in tv-control.service chromium-autolaunch.service; do
  sed -e "s#/home/YOUR_USER#$HOME#g" -e "s#YOUR_USER#$USER#g" -e "s#YOUR_UID#$(id -u)#g" "$SRC_DIR/ColdStart/$service" \
    | sudo tee "/etc/systemd/system/$service" >/dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable tv-control.service chromium-autolaunch.service

# ---------------------------------------------------------
# 9. Self-repair: Wi-Fi, TV page, agent, nightly restart (selfheal.py, as
#    root every minute), hardware watchdog, Wi-Fi power saving off
# ---------------------------------------------------------
step install.selfheal
# Root-owned copy: the script run as root is not the one of ~/AppelerMamie
sudo mkdir -p /usr/local/lib/appelermamie
sed 's/\r$//' "$SRC_DIR/selfheal.py" | sudo tee /usr/local/lib/appelermamie/selfheal.py >/dev/null
for unit in appelermamie-selfheal.service appelermamie-selfheal.timer; do
  sed -e 's/\r$//' -e "s#/home/YOUR_USER#$HOME#g" "$SRC_DIR/ColdStart/$unit" \
    | sudo tee "/etc/systemd/system/$unit" >/dev/null
done
# Hardware watchdog: the Raspberry restarts by itself if the whole system
# freezes (active from the next restart)
sudo mkdir -p /etc/systemd/system.conf.d
sed 's/\r$//' "$SRC_DIR/ColdStart/appelermamie-watchdog.conf" \
  | sudo tee /etc/systemd/system.conf.d/appelermamie-watchdog.conf >/dev/null
# Wi-Fi power saving off: it causes disconnections on the Raspberry
# (for the next connections, and right now)
if sudo test -d /etc/NetworkManager; then
  sudo mkdir -p /etc/NetworkManager/conf.d
  sed 's/\r$//' "$SRC_DIR/ColdStart/appelermamie-wifi.conf" \
    | sudo tee /etc/NetworkManager/conf.d/appelermamie-wifi.conf >/dev/null
fi
sudo iw dev wlan0 set power_save off 2>/dev/null || true
# The TV must not turn on when the Raspberry starts (nightly restart)
boot_config=/boot/firmware/config.txt
if sudo test -f "$boot_config" && ! sudo grep -q '^hdmi_ignore_cec_init=1' "$boot_config"; then
  printf '\n[all]\n# AppelerMamie: the TV is not turned on when the Raspberry starts\nhdmi_ignore_cec_init=1\n' \
    | sudo tee -a "$boot_config" >/dev/null
fi
sudo systemctl daemon-reload
sudo systemctl enable --now appelermamie-selfheal.timer

# ---------------------------------------------------------
# 10. Screen: desktop autologin, no blanking, camera/microphone allowed
# ---------------------------------------------------------
step install.display
if [ -x /usr/bin/raspi-config ]; then
  sudo raspi-config nonint do_boot_behaviour B4 || msg install.displayManual
  sudo raspi-config nonint do_blanking 1 || msg install.displayManual
else
  msg install.displayManual
fi

# Chromium policy: the receiver page may use the camera and the microphone
# without a permission question (nobody is there to click "Allow").
# Domain of SERVER_URL in config.py; both the production server and the test
# server (port 8443, see switch_server.sh) are allowed.
domain="$(cd "$APP_DIR" && "$PYTHON" -c 'import config; print(config.SERVER_URL.split("://", 1)[1].split("/")[0].split(":")[0])' 2>/dev/null || echo "appelermami.fr")"
sudo mkdir -p /etc/chromium/policies/managed
printf '{\n  "VideoCaptureAllowedUrls": ["https://%s", "https://%s:8443"],\n  "AudioCaptureAllowedUrls": ["https://%s", "https://%s:8443"]\n}\n' \
  "$domain" "$domain" "$domain" "$domain" | sudo tee /etc/chromium/policies/managed/appelermamie.json >/dev/null

# ---------------------------------------------------------
# Summary: QR code and identifier to send to the server administrator
# ---------------------------------------------------------
echo
(cd "$APP_DIR" && "$APP_DIR/venv/bin/python3" -c \
  'import sys; from setup_identity import generate_qr_code_text; print(generate_qr_code_text(sys.argv[1]))' \
  "$device_id")
msg install.done device_id="$device_id" code="$device_code"

if ask install.askReboot; then
  msg install.rebooting
  sudo reboot
else
  sudo systemctl restart tv-control.service chromium-autolaunch.service
  msg install.restarted
fi
