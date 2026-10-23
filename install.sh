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
#   bash install.sh --city "Clermont-Ferrand" --postcode 63000 --country France
#                               # place of the weather of the TV home screen
#                               # (each one may be ""), asked at the first installation
#   bash install.sh --update    # update: no question, no restart of the Raspberry
#
# It can be run again at any time to update a Raspberry: the identity
# (identity.json) and the settings of config.py are kept.
# update.sh (remote update, run as root) calls it as root with
# "--update --user <user>": the only case where root is accepted.
# Messages follow the chosen language (texts in i18n.py, "install.*" keys).

set -Eeuo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Clone of the project kept up to date by update.sh (which runs this script
# from a root-owned copy of the verified version: APPELERMAMIE_SRC_DIR)
CLONE_DIR="${APPELERMAMIE_SRC_DIR:-$SRC_DIR}"
PYTHON=python3
export PYTHONDONTWRITEBYTECODE=1

# System packages: audio conversion/playback, TV control (CEC: cec-ctl of
# v4l-utils; cec-utils only for manual checks with cec-client), resolution of
# the screen (wlr-randr, display_mode.py), Python virtual environment (+ build
# tools for evdev), unzip (speech recognition model). The browser (chromium)
# is installed apart: see the "packages" step.
APT_PACKAGES=(ffmpeg alsa-utils v4l-utils cec-utils wlr-randr unzip python3-venv python3-dev build-essential)

# Python packages of the agent (versions tested on Raspberry Pi OS 13 "trixie")
PIP_PACKAGES=("websockets>=13,<18" "evdev>=1.6,<3" "gTTS>=2.5,<3" "qrcode>=7,<9" "vosk>=0.3.45,<0.4")

# Speech recognition model of each language (spoken commands to the robot,
# voice_commands.py): small Vosk models, ~40 MB, checked against their
# SHA-256 before use (a changed file is refused)
VOSK_URL="${APPELERMAMIE_VOSK_URL:-https://alphacephei.com/vosk/models}"
declare -A VOSK_MODELS=(
  [fr]="vosk-model-small-fr-0.22 cabf6180e177eb9b3a9a9d43a437bd5e549f3a7d09525e5d69a3fed787be12ad"
  [en]="vosk-model-small-en-us-0.15 30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498"
  [es]="vosk-model-small-es-0.42 09b239888f633ef2f0b4e09736e3d9936acfd810bc65d53fad45261762c6511f"
)

TOTAL_STEPS=11
STEP=0
STEP_NAME=""
LANG_CHOICE=""
GREETING_CHOICE=""
GREETING_SET=""
WEATHER_CITY=""
WEATHER_POSTCODE=""
WEATHER_COUNTRY=""
WEATHER_SET=""
UPDATE=""
TARGET_USER=""

# ---------------------------------------------------------
# Options
# ---------------------------------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    --lang) LANG_CHOICE="${2:-}"; shift; [ $# -gt 0 ] && shift ;;
    --lang=*) LANG_CHOICE="${1#--lang=}"; shift ;;
    --greeting) GREETING_CHOICE="${2-}"; GREETING_SET=1; shift; [ $# -gt 0 ] && shift ;;
    --greeting=*) GREETING_CHOICE="${1#--greeting=}"; GREETING_SET=1; shift ;;
    --update) UPDATE=1; shift ;;
    --user) TARGET_USER="${2:-}"; shift; [ $# -gt 0 ] && shift ;;
    --city) WEATHER_CITY="${2-}"; WEATHER_SET=1; shift; [ $# -gt 0 ] && shift ;;
    --city=*) WEATHER_CITY="${1#--city=}"; WEATHER_SET=1; shift ;;
    --postcode) WEATHER_POSTCODE="${2-}"; WEATHER_SET=1; shift; [ $# -gt 0 ] && shift ;;
    --postcode=*) WEATHER_POSTCODE="${1#--postcode=}"; WEATHER_SET=1; shift ;;
    --country) WEATHER_COUNTRY="${2-}"; WEATHER_SET=1; shift; [ $# -gt 0 ] && shift ;;
    --country=*) WEATHER_COUNTRY="${1#--country=}"; WEATHER_SET=1; shift ;;
    -h|--help) sed -n '5,26p' "$0"; exit 0 ;;
    *) echo "❌ Unknown option: $1 (see --help)" >&2; exit 1 ;;
  esac
done

# Run as root by update.sh (--update --user <user>): the installation is made
# for that user (sudo then never asks a password). Otherwise, as before: the
# Raspberry user, sudo when needed.
AS_ROOT=""
if [ "$(id -u)" -eq 0 ] && [ -n "$UPDATE" ] && [ -n "$TARGET_USER" ]; then
  AS_ROOT=1
  HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
  [ -n "$HOME" ] || { echo "❌ Unknown user: $TARGET_USER" >&2; exit 1; }
  export HOME USER="$TARGET_USER"
  USER_UID="$(id -u "$TARGET_USER")"
else
  USER_UID="$(id -u)"
fi
APP_DIR="$HOME/AppelerMamie"
LOG_FILE="$HOME/appelermamie-install.log"

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
  # Language chosen on the TV (settings page) first
  if [ -f "$APP_DIR/settings.json" ]; then
    tv_lang="$(sed -n 's/^ *"LANGUAGE": *"\([a-z][a-z]\)".*/\1/p' "$APP_DIR/settings.json" | head -1)"
    default_lang="${tv_lang:-$default_lang}"
  fi
  default_lang="${default_lang:-fr}"
  # Update: the language of the Raspberry, without question
  [ -n "$UPDATE" ] || read -r -p "Langue / Language / Idioma (fr, en, es) [$default_lang] : " LANG_CHOICE || true
  LANG_CHOICE="${LANG_CHOICE:-$default_lang}"
fi
case "$LANG_CHOICE" in
  fr|en|es) ;;
  *) echo "❌ Langue / Language / Idioma : fr, en, es" >&2; exit 1 ;;
esac

if [ "$(id -u)" -eq 0 ] && [ -z "$AS_ROOT" ]; then
  msg install.noRoot >&2
  exit 1
fi

# Run as root: the files made for the user are given back to the user, even
# when the installation stops on an error
if [ -n "$AS_ROOT" ]; then
  trap 'chown -R "$USER:" "$APP_DIR" "$LOG_FILE" 2>/dev/null || true' EXIT
fi

# Greeting of the voice announcement ("Hey grandma, ..."): asked at the first
# installation only (an update keeps the value of config.py)
if [ -z "$GREETING_SET" ] && [ -z "$UPDATE" ] && [ ! -f "$APP_DIR/config.py" ]; then
  # (question printed apart: read -p shows nothing when the answers come from a pipe)
  printf '%s' "$(msg install.askGreeting)"
  read -r GREETING_CHOICE || true
  echo
  GREETING_SET=1
fi

# Place of the weather of the home screen (town, postal code, country): asked
# at the first installation only (an update keeps the values of config.py)
if [ -z "$WEATHER_SET" ] && [ -z "$UPDATE" ] && [ ! -f "$APP_DIR/config.py" ]; then
  printf '%s' "$(msg install.askCity)"
  read -r WEATHER_CITY || true
  printf '%s' "$(msg install.askPostcode)"
  read -r WEATHER_POSTCODE || true
  printf '%s' "$(msg install.askCountry)"
  read -r WEATHER_COUNTRY || true
  echo
  WEATHER_SET=1
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
  if [ -z "$UPDATE" ] && ! ask install.askContinue; then
    msg install.stopped
    exit 1
  fi
fi

if [ -z "$AS_ROOT" ]; then
  msg install.sudo
  sudo -v
  # Keep the sudo rights during the whole installation
  ( while kill -0 "$$" 2>/dev/null; do sudo -n true; sleep 50; done ) 2>/dev/null &
fi

# ---------------------------------------------------------
# 2. System packages
# ---------------------------------------------------------
step install.packages
# An update only installs them when the list changed since the last time
packages_file="$APP_DIR/.apt-packages"
packages="${APT_PACKAGES[*]} chromium"
if [ -n "$UPDATE" ] && [ "$(cat "$packages_file" 2>/dev/null)" = "$packages" ]; then
  msg install.packagesUnchanged
else
  sudo apt-get update -q
  sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${APT_PACKAGES[@]}"
  # Chromium is installed if missing, but never upgraded by this script: a new
  # version once stopped the camera and the microphone of the calls (11/10/2026).
  sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-upgrade chromium
  mkdir -p "$APP_DIR"
  echo "$packages" > "$packages_file"
fi

# ---------------------------------------------------------
# 3. Project files, copied flat into ~/AppelerMamie
# ---------------------------------------------------------
step install.files dir="$APP_DIR"
mkdir -p "$APP_DIR"

# Files created by another user (e.g. with sudo during a manual install)
# cannot be replaced: they are given back to the Raspberry user.
if [ -z "$AS_ROOT" ] && [ -n "$(find "$APP_DIR" \( ! -user "$USER_UID" -o ! -writable \) -print -quit 2>/dev/null)" ]; then
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

# Installed version (sent to the server by the agent): given by update.sh, or
# the tag of the cloned project (git), or "unknown" for a copied folder
version="${APPELERMAMIE_VERSION:-}"
if [ -z "$version" ] && command -v git >/dev/null && [ -d "$CLONE_DIR/.git" ]; then
  version="$(git -c safe.directory="$CLONE_DIR" -C "$CLONE_DIR" describe --tags --always --dirty 2>/dev/null || true)"
fi
echo "${version:-unknown}" > "$APP_DIR/VERSION"

# New config.py = the one of the project + the values of the previous one +
# the chosen language and greeting, prepared in a temporary file then moved in
# one go. A MOUSE_DEVICE such as /dev/input/event4 changes with the USB port:
# it is replaced by the automatic detection. An older config.py without
# GREETING_NAME keeps the announcement it had ("Hey grandma, ...").
new_config="$APP_DIR/.config.py.new"
sed 's/\r$//' "$SRC_DIR/config.py" > "$new_config"
config_notes="$("$PYTHON" - "$new_config" "$old_config" "$LANG_CHOICE" "$GREETING_SET" "$GREETING_CHOICE"   "$WEATHER_SET" "$WEATHER_CITY" "$WEATHER_POSTCODE" "$WEATHER_COUNTRY" <<'PY'
import json
import os
import re
import sys

new_path, old_path, lang, greeting_set, greeting = sys.argv[1:6]
weather_set, weather = sys.argv[6], dict(zip(("WEATHER_CITY", "WEATHER_POSTCODE", "WEATHER_COUNTRY"), sys.argv[7:10]))
KEPT = ("SERVER_URL", "UNAUTHORIZED_RETRY_DELAY", "MOUSE_DEVICE", "MOUSE_RETRY_DELAY",
        "HDMI_PORT", "AUDIO_DEVICE", "CALL_AUDIO_OUTPUT", "SCREEN_MODE", "VOICE_REACTION", "RINGTONE_PATH", "CALL_DURATION", "MAX_CACHED_CALLS",
        "MAX_CALLER_NAME_LENGTH", "VOICE_VOLUME", "RINGTONE_VOLUME", "QUIET_START_HOUR", "QUIET_END_HOUR",
        "NIGHTLY_REBOOT_HOUR",
        "GREETING_NAME", "WEATHER_CITY", "WEATHER_POSTCODE", "WEATHER_COUNTRY", "VOICE_COMMANDS", "TV_NAME",
        "RADIO_STATIONS")
# Settings written on several lines (a list from "[" to the "]" at the start of a line)
BLOCKS = ("RADIO_STATIONS",)
# The stations written in config.py before 19/10/2026 (Paris): not one's own
# list, they give way to the stations of the country of the TV (None)
FORMER_STATIONS = {
    ("87.8", "https://icecast.radiofrance.fr/franceinter-midfi.mp3"), ("91.7", "https://icecast.radiofrance.fr/francemusique-midfi.mp3"),
    ("93.5", "https://icecast.radiofrance.fr/franceculture-midfi.mp3"), ("105.1", "https://icecast.radiofrance.fr/fip-midfi.mp3"),
    ("105.5", "https://icecast.radiofrance.fr/franceinfo-midfi.mp3"), ("104.3", "http://icecast.rtl.fr/rtl-1-44-128"),
    ("104.7", "https://stream.europe1.fr/europe1.mp3"), ("90.4", "https://streaming.nrjaudio.fm/oug7girb92oc"),
    ("91.3", "https://cdnradio.streamakaci.com/cheriefm1.mp3"), ("100.3", "https://scdn.nrjaudio.fm/adwz2/fr/30001/mp3_128.mp3"),
    ("103.9", "https://rfm.lmn.fm/rfm.mp3"), ("101.1", "http://radioclassique.ice.infomaniak.ch/radioclassique-high.mp3"),
}
# Greeting of the announcement before GREETING_NAME existed
FORMER_GREETING = {"fr": "mamie", "en": "grandma", "es": "abuela"}


def setting(key, text):
    match = re.search(rf"^{key} *= *\[.*?^\]$", text, re.M | re.S) if key in BLOCKS else None
    if not match:
        match = re.search(rf"^{key} *=.*$", text, re.M)
    return match.group(0) if match else None


def former_stations(block):
    """The list of stations of the project before 19/10/2026 (not changed by hand)."""
    pairs = set(re.findall(r'"frequency": *([0-9.]+), *"url": *"([^"]+)"', block))
    return pairs == FORMER_STATIONS and block.count('"url"') == len(FORMER_STATIONS)


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
        if key == "RADIO_STATIONS" and former_stations(old_line):
            print("radio=country")
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


def set_weather():
    global new
    for key, value in weather.items():
        clean = "".join(c for c in value.strip()[:60] if c.isalnum() or c in " -'.,").strip()
        line = f'{key} = "{clean}"' if clean else f"{key} = None"
        new = re.sub(rf"^{key} *=.*$", line, new, count=1, flags=re.M)
    print("weather=set")


if weather_set:
    set_weather()

# Settings changed on the TV (settings.json): written here, the file is then
# removed (one place for the settings). The options of this script win.
settings_path = os.path.join(os.path.dirname(new_path), "settings.json")
try:
    with open(settings_path, encoding="utf-8") as f:
        tv_settings = json.load(f)
except (OSError, ValueError):
    tv_settings = None
if isinstance(tv_settings, dict):
    volume = tv_settings.get("RINGTONE_VOLUME")
    if isinstance(volume, (int, float)) and not isinstance(volume, bool) and 0.1 <= volume <= 1.0:
        new = re.sub(r"^RINGTONE_VOLUME *=.*$", f"RINGTONE_VOLUME = {round(volume, 2)}", new, count=1, flags=re.M)
    volume = tv_settings.get("VOICE_VOLUME")
    if isinstance(volume, (int, float)) and not isinstance(volume, bool) and 0.15 <= volume <= 1.96:
        new = re.sub(r"^VOICE_VOLUME *=.*$", f"VOICE_VOLUME = {round(volume, 2)}", new, count=1, flags=re.M)
    for key in ("QUIET_START_HOUR", "QUIET_END_HOUR"):
        hour = tv_settings.get(key)
        if isinstance(hour, int) and not isinstance(hour, bool) and 0 <= hour <= 23:
            new = re.sub(rf"^{key} *=.*$", f"{key} = {hour}", new, count=1, flags=re.M)
    if not weather_set and any(key in tv_settings for key in weather):
        weather = {key: tv_settings.get(key) or "" for key in weather}
        set_weather()
    if "TV_NAME" in tv_settings:
        clean = "".join(c for c in str(tv_settings.get("TV_NAME") or "").strip()[:30] if c.isalnum() or c in " -'.,").strip()
        line = f'TV_NAME = "{clean}"' if clean else "TV_NAME = None"
        new = re.sub(r"^TV_NAME *=.*$", line, new, count=1, flags=re.M)
    print("settings=absorbed")

new = re.sub(r"^LANGUAGE *=.*$", f'LANGUAGE = "{lang}"', new, count=1, flags=re.M)

with open(new_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(new)
PY
)"
mv "$new_config" "$APP_DIR/config.py"
if grep -q "^settings=absorbed" <<< "$config_notes"; then
  rm -f "$APP_DIR/settings.json"
fi
if [ -n "$old_config" ]; then
  msg install.configKept backup="$old_config"
fi
if grep -q "^radio=country$" <<< "$config_notes"; then
  msg install.radioCountry
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
if grep -q "^weather=set$" <<< "$config_notes"; then
  place="$(sed -n 's/^WEATHER_\(CITY\|POSTCODE\|COUNTRY\) *= *"\(.*\)".*/\2/p' "$APP_DIR/config.py" | paste -sd ' ' -)"
  if grep -q '^WEATHER_\(CITY\|POSTCODE\) *= *"' "$APP_DIR/config.py"; then
    msg install.weather place="$place"
  else
    msg install.noWeather
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

# Speech recognition model of the language (once; again if the language
# changed). Never fatal: without it, there are no spoken commands.
read -r vosk_name vosk_sha <<< "${VOSK_MODELS[$LANG_CHOICE]}"
if [ "$(cat "$APP_DIR/vosk-model/.name" 2>/dev/null)" != "$vosk_name" ]; then
  vosk_tmp="$(mktemp -d)"
  if curl -sSfL --max-time 900 -o "$vosk_tmp/model.zip" "$VOSK_URL/$vosk_name.zip"      && echo "$vosk_sha  $vosk_tmp/model.zip" | sha256sum -c --quiet -      && unzip -q "$vosk_tmp/model.zip" -d "$vosk_tmp" && [ -d "$vosk_tmp/$vosk_name" ]; then
    rm -rf "$APP_DIR/vosk-model"
    mv "$vosk_tmp/$vosk_name" "$APP_DIR/vosk-model"
    echo "$vosk_name" > "$APP_DIR/vosk-model/.name"
    msg install.voiceModel name="$vosk_name"
  else
    msg install.voiceModelFailed
  fi
  rm -rf "$vosk_tmp"
fi

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
  sed -e "s#/home/YOUR_USER#$HOME#g" -e "s#YOUR_USER#$USER#g" -e "s#YOUR_UID#$USER_UID#g" "$SRC_DIR/ColdStart/$service" \
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
# 10. Remote updates (update.sh, as root, when the agent drops the request
#     of the server): only versions signed by the key of allowed_signers
# ---------------------------------------------------------
step install.updates
# Written beside then moved: update.sh may be the script running this
# installation (bash reads it as it goes: it must never be changed in place)
sed 's/\r$//' "$SRC_DIR/update.sh" | sudo tee /usr/local/lib/appelermamie/update.sh.new >/dev/null
sudo mv -f /usr/local/lib/appelermamie/update.sh.new /usr/local/lib/appelermamie/update.sh
# The signing key is installed once (root only can change it afterwards: a
# version cannot replace the key that checks it)
sudo mkdir -p /etc/appelermamie
if ! sudo test -f /etc/appelermamie/allowed_signers; then
  sed 's/\r$//' "$SRC_DIR/ColdStart/allowed_signers" | sudo tee /etc/appelermamie/allowed_signers >/dev/null
fi
for unit in appelermamie-update.service appelermamie-update.path; do
  sed -e 's/\r$//' -e "s#/home/YOUR_USER/AppelerMamie-src#$CLONE_DIR#g" -e "s#/home/YOUR_USER#$HOME#g" \
      -e "s#YOUR_USER#$USER#g" "$SRC_DIR/ColdStart/$unit" \
    | sudo tee "/etc/systemd/system/$unit" >/dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable --now appelermamie-update.path
if [ ! -d "$CLONE_DIR/.git" ]; then
  msg install.updatesNoClone
fi

# ---------------------------------------------------------
# 11. Screen: desktop autologin, no blanking, camera/microphone allowed
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
if [ -n "$UPDATE" ]; then
  # Update: the programs are restarted, not the Raspberry
  sudo systemctl restart tv-control.service chromium-autolaunch.service
  msg install.updated version="$(cat "$APP_DIR/VERSION")"
  exit 0
fi

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
