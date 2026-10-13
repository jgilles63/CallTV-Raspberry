#!/bin/bash
# ============================================
# FILE: update.sh
# ============================================
# Updates the Raspberry to a published version of the public repository
# (ROADMAP 3.6). Run as root by appelermamie-update.service (root-owned copy in
# /usr/local/lib/appelermamie), started when the agent drops the file
# ~/AppelerMamie/update_request (it contains only a version, e.g. v0.2.1: the
# server only tells which version exists, it never sends code or commands).
#
#   update.sh <user> <project folder>     e.g. update.sh pi /home/pi/AppelerMamie-src
#
# Steps: waits for the end of a call; downloads the versions (git fetch, as the
# user); accepts the version only if its tag is SIGNED by the key of
# /etc/appelermamie/allowed_signers (installed once, root-owned) and newer than
# the installed one; checks it out; runs install.sh --update; waits for the
# agent to be connected to the server again, otherwise goes back to the
# previous version. Result in /var/lib/appelermamie/update.json (health report).
set -uo pipefail

USER_NAME="${1:-}"
SRC_DIR="${2:-}"
SIGNERS="${APPELERMAMIE_SIGNERS:-/etc/appelermamie/allowed_signers}"
STATE_DIR="${APPELERMAMIE_STATE_DIR:-/var/lib/appelermamie}"
STATE_FILE="$STATE_DIR/update.json"
LOCK_FILE="${APPELERMAMIE_LOCK:-/run/appelermamie-update.lock}"
CALL_WAIT="${APPELERMAMIE_CALL_WAIT:-1800}"          # end of a call waited for at most 30 min
AGENT_WAIT="${APPELERMAMIE_AGENT_WAIT:-180}"         # agent connected again within 3 min
POLL="${APPELERMAMIE_POLL:-10}"
VERSION_PATTERN='^v[0-9]+\.[0-9]+\.[0-9]+$'

log() { echo "🔄 Update: $*"; }

[ -n "$USER_NAME" ] && [ -n "$SRC_DIR" ] || { echo "Usage: update.sh <user> <project folder>" >&2; exit 2; }
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
[ -n "$HOME_DIR" ] || { log "unknown user $USER_NAME"; exit 2; }
APP_DIR="$HOME_DIR/AppelerMamie"
REQUEST_FILE="$APP_DIR/update_request"
AGENT_STATE="$APP_DIR/agent_state.json"

# Commands of the user, with its own home folder (git reads its configuration there)
as_user() { runuser -u "$USER_NAME" -- env HOME="$HOME_DIR" "$@"; }
# git run as root on the folder of the user (read only)
root_git() { git -c safe.directory="$SRC_DIR" -C "$SRC_DIR" "$@"; }

# Result kept for the health report: {"time", "from", "to", "result", "reason"}
record() {
  mkdir -p "$STATE_DIR"
  printf '{"time": %s, "from": "%s", "to": "%s", "result": "%s", "reason": "%s"}\n' \
    "$(date +%s)" "$CURRENT" "$VERSION" "$1" "${2:-}" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
  log "$1${2:+ ($2)}: ${CURRENT:-?} -> ${VERSION:-?}"
}
fail() { record failed "$1"; exit 1; }

# One update at a time
exec 9>"$LOCK_FILE"
flock -n 9 || { log "already running"; exit 0; }

# --- The request: only a version number ---
VERSION=""
CURRENT=""
if [ -f "$REQUEST_FILE" ]; then
  VERSION="$(head -c 40 "$REQUEST_FILE" | head -n 1 | tr -d '[:space:]')"
  rm -f "$REQUEST_FILE"
fi
[ -n "$VERSION" ] || { log "no request"; exit 0; }
[[ "$VERSION" =~ $VERSION_PATTERN ]] || { VERSION="invalid"; fail "invalid version"; }

[ -d "$SRC_DIR/.git" ] || fail "not a git clone: $SRC_DIR"
[ -f "$SIGNERS" ] || fail "no signing key ($SIGNERS)"

CURRENT_COMMIT="$(root_git rev-parse HEAD 2>/dev/null)" || fail "cannot read the installed version"
CURRENT="$(root_git describe --tags --exact-match HEAD 2>/dev/null || echo "${CURRENT_COMMIT:0:7}")"

# --- Never during a call (state written every 30 s by the agent) ---
agent_field() {
  python3 - "$AGENT_STATE" "$1" <<'PY' 2>/dev/null
import json, sys, time
try:
    state = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
fresh = time.time() - state.get("time", 0) < 120
value = state.get(sys.argv[2])
if sys.argv[2] == "time":
    print(int(state.get("time", 0)))
else:
    print("yes" if fresh and value else "no")
PY
}
waited=0
while [ "$(agent_field inCall)" = yes ]; do
  [ "$waited" -ge "$CALL_WAIT" ] && fail "call in progress"
  [ "$waited" -eq 0 ] && log "call in progress, waiting for its end"
  sleep "$POLL"
  waited=$((waited + POLL))
done

# --- Download and check the version ---
log "downloading $VERSION"
as_user git -C "$SRC_DIR" fetch --quiet --force --tags origin || fail "download failed"
root_git rev-parse -q --verify "refs/tags/$VERSION" >/dev/null || fail "unknown version"
root_git -c gpg.format=ssh -c gpg.ssh.allowedSignersFile="$SIGNERS" tag -v "$VERSION" >/dev/null 2>&1 \
  || fail "signature not valid"
TARGET="$(root_git rev-parse "$VERSION^{commit}")" || fail "unknown version"

if [[ "$CURRENT" =~ $VERSION_PATTERN ]]; then
  [ "$CURRENT" = "$VERSION" ] && { record unchanged "already installed"; exit 0; }
  newest="$(printf '%s\n%s\n' "$CURRENT" "$VERSION" | sort -V | tail -n 1)"
  [ "$newest" = "$VERSION" ] || fail "older than the installed version"
fi

# --- Install ---
# install_version <commit> <version name>: the clone of the user is put on this
# version, but install.sh is run (as root) from a root-owned copy of the
# verified commit, never from the folder of the user (which the user can change).
install_version() {
  as_user git -C "$SRC_DIR" -c advice.detachedHead=false checkout --quiet --force "$1" || return 1
  local tree
  tree="$(mktemp -d /tmp/appelermamie-update.XXXXXX)" || return 1
  if ! root_git archive "$1" | tar -x -C "$tree"; then
    rm -rf "$tree"
    return 1
  fi
  APPELERMAMIE_VERSION="$2" APPELERMAMIE_SRC_DIR="$SRC_DIR" bash "$tree/install.sh" --update --user "$USER_NAME"
  local status=$?
  rm -rf "$tree"
  return $status
}

agent_back() {
  local since="$1" waited=0
  while [ "$waited" -lt "$AGENT_WAIT" ]; do
    sleep "$POLL"
    waited=$((waited + POLL))
    local written
    written="$(agent_field time || echo 0)"
    if [ "${written:-0}" -gt "$since" ] && [ "$(agent_field registered)" = yes ]; then
      return 0
    fi
  done
  return 1
}

log "installing $VERSION (installed: $CURRENT)"
record installing
started="$(date +%s)"
if install_version "$TARGET" "$VERSION"; then
  if agent_back "$started"; then
    record ok
    exit 0
  fi
  reason="agent not connected after the update"
else
  reason="installation failed"
fi

# --- Something went wrong: back to the previous version ---
log "$VERSION does not work ($reason), back to $CURRENT"
if install_version "$CURRENT_COMMIT" "$CURRENT"; then
  record "rolled back" "$reason"
else
  record failed "$reason, rollback failed"
fi
exit 1
