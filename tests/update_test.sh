#!/bin/bash
# Tests update.sh (update to a signed version) with real git repositories and a
# real signing key made for the test: an "origin" repository publishes
# versions (signed tags), the clone of the Raspberry is updated from it.
# install.sh of the published versions is a fake one (it writes what it was
# asked and the state of the agent); runuser, getent and flock are simulated.
# Works on Linux and on Windows (Git Bash). Needs git and ssh-keygen.
#
# Usage: bash tests/update_test.sh
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"   # Raspberry_receiver/
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
REALPY=""
for c in python3 python; do
  if "$c" -c "import sys" >/dev/null 2>&1; then REALPY="$(command -v "$c")"; break; fi
done
pass=0; fail=0
check() { if eval "$2"; then pass=$((pass+1)); echo "✅ $1"; else fail=$((fail+1)); echo "❌ $1"; fi; }

HOME_DIR="$T/home/pi"
APP="$HOME_DIR/AppelerMamie"
SRC="$HOME_DIR/AppelerMamie-src"
ORIGIN="$T/origin"
mkdir -p "$APP" "$T/bin" "$T/state"

# --- Simulated system commands ---
printf '#!/bin/bash\n[ "$1" = passwd ] && [ "$2" = pi ] && echo "pi:x:1000:1000::%s:/bin/bash" || exit 2\n' "$HOME_DIR" > "$T/bin/getent"
printf '#!/bin/bash\n# runuser -u <user> -- command...\nshift 3\nexec "$@"\n' > "$T/bin/runuser"
printf '#!/bin/bash\nexit 0\n' > "$T/bin/flock"
printf '#!/bin/bash\nexec "%s" "$@"\n' "$REALPY" > "$T/bin/python3"
chmod +x "$T/bin/"*

# --- Signing keys: the trusted one, and another one ---
ssh-keygen -q -t ed25519 -N "" -C test -f "$T/key"
ssh-keygen -q -t ed25519 -N "" -C other -f "$T/other"
printf 'release@example.org namespaces="git" %s\n' "$(cut -d' ' -f1,2 "$T/key.pub")" > "$T/signers"

# --- Origin repository: versions published as tags ---
git init -q "$ORIGIN"
git -C "$ORIGIN" config user.name test
git -C "$ORIGIN" config user.email release@example.org
git -C "$ORIGIN" config gpg.format ssh
git -C "$ORIGIN" config core.autocrlf false
cat > "$ORIGIN/install.sh" <<EOF
#!/bin/bash
# Fake install.sh: tells what it was asked, from where, and starts the "agent"
echo "\$(basename "\$(dirname "\$0")") \$* version=\${APPELERMAMIE_VERSION:-} content=\$(cat "\$(dirname "\$0")/content.txt")" >> "$T/install.log"
# install_fails: version for which the installation fails
grep -qx "\${APPELERMAMIE_VERSION:-}" "$T/install_fails" 2>/dev/null && exit 1
[ -f "$T/agent_dead" ] && exit 0
printf '{"time": %s, "registered": true, "inCall": false}' "\$(( \$(date +%s) + 1 ))" > "$APP/agent_state.json"
EOF
publish() {  # publish <version> <content> [sign key|unsigned]
  echo "$2" > "$ORIGIN/content.txt"
  git -C "$ORIGIN" add -A && git -C "$ORIGIN" commit -q -m "$1"
  case "${3:-$T/key}" in
    unsigned) git -C "$ORIGIN" tag -a "$1" -m "$1" ;;
    *) git -C "$ORIGIN" -c user.signingkey="${3:-$T/key}.pub" tag -s "$1" -m "$1" ;;
  esac
}
publish v0.1.0 "content 0.1.0"
git clone -q -c core.autocrlf=false "$ORIGIN" "$SRC"
git -C "$SRC" -c advice.detachedHead=false checkout -q v0.1.0
publish v0.2.0 "content 0.2.0"

# update <version>: drops the request as the agent does, then runs update.sh
update() {
  [ -n "$1" ] && printf '%s\n' "$1" > "$APP/update_request"
  : > "$T/install.log"
  env PATH="$T/bin:$PATH" APPELERMAMIE_SIGNERS="$T/signers" APPELERMAMIE_STATE_DIR="$T/state" \
    APPELERMAMIE_LOCK="$T/lock" APPELERMAMIE_CALL_WAIT="${CALL_WAIT:-30}" APPELERMAMIE_AGENT_WAIT=3 APPELERMAMIE_POLL=1 \
    bash "$REPO/update.sh" pi "$SRC" > "$T/out.txt" 2>&1
  echo $? > "$T/rc.txt"
}
state() { "$REALPY" -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d[sys.argv[2]])' "$T/state/update.json" "$1"; }
head_is() { [ "$(git -C "$SRC" rev-parse HEAD)" = "$(git -C "$SRC" rev-parse "$1^{commit}")" ]; }

echo "=== 1. Signed newer version"
update v0.2.0
check "update done (exit 0)" '[ "$(cat $T/rc.txt)" = 0 ]'
check "result kept: ok, from v0.1.0 to v0.2.0" '[ "$(state result)" = ok ] && [ "$(state from)" = v0.1.0 ] && [ "$(state to)" = v0.2.0 ]'
check "clone of the user on v0.2.0" 'head_is v0.2.0'
check "install.sh --update --user pi run once, with the version" '[ "$(wc -l < $T/install.log)" = 1 ] && grep -q -- "--update --user pi version=v0.2.0" $T/install.log'
check "install.sh run from a copy of the verified commit, not from the folder of the user" 'grep -q "^appelermamie-update\.[^ ]* .*content=content 0.2.0" $T/install.log'
check "request file removed" '[ ! -e $APP/update_request ]'
check "temporary copy removed" '! ls -d /tmp/appelermamie-update.* >/dev/null 2>&1'

echo "=== 2. Same version again"
update v0.2.0
check "nothing installed: already installed" '[ "$(cat $T/rc.txt)" = 0 ] && [ "$(state result)" = unchanged ] && [ ! -s $T/install.log ]'

echo "=== 3. Older version (signed)"
update v0.1.0
check "refused: older than the installed version" '[ "$(cat $T/rc.txt)" != 0 ] && [ "$(state reason)" = "older than the installed version" ] && head_is v0.2.0 && [ ! -s $T/install.log ]'

echo "=== 4. Version not signed"
publish v0.3.0 "content 0.3.0" unsigned
update v0.3.0
check "refused: signature not valid, nothing changed" '[ "$(state reason)" = "signature not valid" ] && head_is v0.2.0 && [ ! -s $T/install.log ]'

echo "=== 5. Version signed by another key"
publish v0.3.1 "content 0.3.1" "$T/other"
update v0.3.1
check "refused: signature not valid" '[ "$(state reason)" = "signature not valid" ] && head_is v0.2.0 && [ ! -s $T/install.log ]'

echo "=== 6. Invalid or unknown version"
update 'v1; rm -rf ~'
check "invalid version: refused before any download" '[ "$(state reason)" = "invalid version" ] && head_is v0.2.0'
update v9.9.9
check "unknown version: refused" '[ "$(state reason)" = "unknown version" ] && head_is v0.2.0'

echo "=== 7. Call in progress"
publish v0.4.0 "content 0.4.0"
printf '{"time": %s, "registered": true, "inCall": true}' "$(date +%s)" > "$APP/agent_state.json"
CALL_WAIT=2 update v0.4.0
check "call that does not end: not updated" '[ "$(state reason)" = "call in progress" ] && head_is v0.2.0 && [ ! -s $T/install.log ]'
printf '{"time": %s, "registered": true, "inCall": true}' "$(( $(date +%s) - 600 ))" > "$APP/agent_state.json"
update v0.4.0
check "state of the agent too old (agent stuck): not trusted as a call, updated" '[ "$(state result)" = ok ] && head_is v0.4.0'

echo "=== 8. The agent does not connect after the update"
publish v0.5.0 "content 0.5.0"
rm -f "$APP/agent_state.json"
touch "$T/agent_dead"
update v0.5.0
rm -f "$T/agent_dead"
check "back to the previous version" '[ "$(cat $T/rc.txt)" != 0 ] && [ "$(state result)" = "rolled back" ] && head_is v0.4.0'
check "installed twice: v0.5.0 then v0.4.0 again" '[ "$(wc -l < $T/install.log)" = 2 ] && sed -n 2p $T/install.log | grep -q "version=v0.4.0 content=content 0.4.0"'

echo "=== 9. install.sh fails"
echo v0.5.0 > "$T/install_fails"
update v0.5.0
rm -f "$T/install_fails"
check "back to the previous version, reason given" '[ "$(state result)" = "rolled back" ] && [ "$(state reason)" = "installation failed" ] && head_is v0.4.0'
echo v0.4.0 > "$T/install_fails"
echo v0.5.0 >> "$T/install_fails"
update v0.5.0
check "rollback fails too: told" '[ "$(state result)" = failed ] && [ "$(state reason)" = "installation failed, rollback failed" ]'

echo "=== 10. No request, folder not cloned"
update ""
check "no request: nothing done" '[ "$(cat $T/rc.txt)" = 0 ] && grep -q "no request" $T/out.txt'
mv "$SRC/.git" "$SRC/.git-away"
update v0.5.0
mv "$SRC/.git-away" "$SRC/.git"
check "project folder not cloned with git: told" '[ "$(cat $T/rc.txt)" != 0 ] && [[ "$(state reason)" == "not a git clone"* ]]'

echo
echo "$pass passed, $fail failed"
[ "$fail" = 0 ]
