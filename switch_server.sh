#!/bin/bash
# ============================================
# FILE: switch_server.sh
# ============================================
# Switches this Raspberry between the production server and the test server
# (copy of the server used during development, port 8443).
#
# Usage, as the Raspberry user (NOT with sudo):
#   bash ~/AppelerMamie/switch_server.sh          # shows the current server
#   bash ~/AppelerMamie/switch_server.sh test     # test server
#   bash ~/AppelerMamie/switch_server.sh prod     # production server
#
# Only SERVER_URL in config.py is changed: the agent uses it, and so does the
# TV page (launch_chromium.sh reads it). install.sh keeps this setting when it
# is run again. The agent and the TV page are then restarted.
# Messages follow LANGUAGE of config.py (texts in i18n.py, "switch.*" keys).

set -Eeuo pipefail

# Addresses of the two servers (to change if the domain changes)
PROD_URL="wss://appelermami.fr"
TEST_URL="wss://appelermami.fr:8443"

APP_DIR="$HOME/AppelerMamie"
CONFIG="$APP_DIR/config.py"
export PYTHONDONTWRITEBYTECODE=1

if [ ! -f "$CONFIG" ] || [ ! -f "$APP_DIR/i18n.py" ]; then
  echo "❌ $CONFIG ?  →  bash install.sh" >&2
  exit 1
fi

# Translated message: msg <key> [name=value ...]
msg() {
  (cd "$APP_DIR" && python3 -c '
import sys, i18n
key, *pairs = sys.argv[1:]
print(i18n.t(key, **dict(pair.split("=", 1) for pair in pairs)))' "$@")
}

if [ "$(id -u)" -eq 0 ]; then
  msg switch.noRoot >&2
  exit 1
fi

current_url() {
  sed -n 's/^SERVER_URL = "\(.*\)".*/\1/p' "$CONFIG" | head -n 1
}

server_name() {
  case "$1" in
    "$PROD_URL") msg switch.prodName ;;
    "$TEST_URL") msg switch.testName ;;
    *) msg switch.otherName url="$1" ;;
  esac
}

case "${1:-status}" in
  test) target="$TEST_URL" ;;
  prod) target="$PROD_URL" ;;
  status)
    msg switch.current server="$(server_name "$(current_url)")"
    msg switch.usage
    exit 0
    ;;
  *)
    msg switch.usage >&2
    exit 1
    ;;
esac

if ! grep -q '^SERVER_URL = "' "$CONFIG"; then
  msg switch.noSetting file="$CONFIG" >&2
  exit 1
fi

if [ "$(current_url)" = "$target" ]; then
  msg switch.already server="$(server_name "$target")"
  exit 0
fi

sed -i "s#^SERVER_URL = \".*\"#SERVER_URL = \"$target\"#" "$CONFIG"
msg switch.done server="$(server_name "$(current_url)")"

msg switch.restarting
sudo systemctl restart tv-control.service chromium-autolaunch.service
msg switch.restarted
