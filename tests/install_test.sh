#!/bin/bash
# Runs the real install.sh in a fake home, in a temporary folder, with stubbed
# system commands (sudo, apt-get, systemctl...): /etc, /usr/local and /boot are
# redirected to a fake system, nothing is installed on the real one.
# Works on Linux and on Windows (Git Bash). Needs python3 and internet access
# (pip installs qrcode in the fake venv).
#
# Usage: bash tests/install_test.sh
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"   # Raspberry_receiver/
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
# First Python that really runs (on Windows, "python3" can be a Microsoft Store shortcut)
REALPY=""
for c in python3 python; do
  if "$c" -c "import sys" >/dev/null 2>&1; then REALPY="$(command -v "$c")"; break; fi
done
pass=0; fail=0
check() { if eval "$2"; then pass=$((pass+1)); echo "✅ $1"; else fail=$((fail+1)); echo "❌ $1"; fi; }
# Native path of a file, for Python and Windows programs (unchanged on Linux)
native() { if command -v cygpath >/dev/null; then cygpath -w "$1"; else echo "$1"; fi; }

make_stubs() {
  rm -rf "$T/bin"; mkdir -p "$T/bin"
  cat > "$T/bin/sudo" <<EOF
#!/bin/bash
echo "SUDO \$*" >> "$T/calls.log"
case "\$1" in -v|-n) exit 0 ;; esac
args=(); for a in "\$@"; do a="\${a//\/etc\//$T/root/etc/}"; a="\${a//\/usr\/local\//$T/root/usr/local/}"; args+=("\${a//\/boot\//$T/root/boot/}"); done
exec "\${args[@]}"
EOF
  for c in systemctl usermod reboot chown; do
    printf '#!/bin/bash\necho "%s $*" >> "%s/calls.log"\n' "$c" "$T" > "$T/bin/$c"
  done
  printf '#!/bin/bash\necho "apt-get $*" >> "%s/calls.log"\n[ -f "%s/apt_fails" ] && exit 100\nexit 0\n' "$T" "$T" > "$T/bin/apt-get"
  cat > "$T/bin/getent" <<'EOF'
#!/bin/bash
[ "$1" = hosts ] && exit 0
case "$2" in input|video|audio) echo "$2:x:1:"; exit 0 ;; esac
exit 2
EOF
  printf '#!/bin/bash\ncp "${@: -2:1}" "${@: -1}"\n' > "$T/bin/ffmpeg"
  printf '#!/bin/bash\nexit 0\n' > "$T/bin/labwc"
  cat > "$T/bin/python3" <<EOF
#!/bin/bash
if [ "\${1:-}" = "-m" ] && [ "\${2:-}" = "venv" ]; then
  mkdir -p "\$3/bin" "\$3/lib"
  printf 'import os
if not hasattr(os, "fchmod"):
    os.fchmod = lambda fd, mode: None
' > "\$3/lib/sitecustomize.py"
  printf '#!/bin/bash\nPYTHONPATH="%s/lib" exec "$REALPY" "\$@"\n' "\$3" > "\$3/bin/python3"
  printf '#!/bin/bash\necho "pip \$*" >> "$T/calls.log"\n"$REALPY" -m pip install -q --disable-pip-version-check --no-cache-dir --target "%s/lib" qrcode >/dev/null 2>&1\n' "\$3" > "\$3/bin/pip"
  chmod +x "\$3/bin/python3" "\$3/bin/pip"
  exit 0
fi
exec "$REALPY" "\$@"
EOF
  chmod +x "$T/bin/"*
}

# run <stdin answers> <script> [args...]
run() {
  local input="$1"; shift
  printf '%b' "$input" | env HOME="$T/home/ofic" USERPROFILE="$(native "$T/home/ofic")" USER=ofic \
    PATH="$T/bin:$PATH" PYTHONIOENCODING=utf-8 bash "$@" > "$T/out.txt" 2>&1
  echo $? > "$T/rc.txt"
}

fresh() {
  rm -rf "$T/home" "$T/root" "$T/src" "$T/calls.log" "$T/apt_fails"
  mkdir -p "$T/home/ofic" "$T/root/etc/systemd/system" "$T/root/etc/NetworkManager" "$T/root/boot/firmware" "$T/src"
  printf '[all]\ndtparam=audio=on\n' > "$T/root/boot/firmware/config.txt"
  cp -r "$REPO" "$T/src/Raspberry_receiver"
  rm -rf "$T/src/Raspberry_receiver/__pycache__"
}

APP="$T/home/ofic/AppelerMamie"
make_stubs

echo "=== 1. First installation (--lang es, no restart)"
fresh
run 'n\n' "$T/src/Raspberry_receiver/install.sh" --lang es
check "the script ends without error" '[ "$(cat $T/rc.txt)" = 0 ]'
check "messages in Spanish" 'grep -q "INSTALACIÓN DE LLAMAR A LA ABUELA" $T/out.txt && grep -q "\[10/10\] Pantalla" $T/out.txt'
check "files copied flat (agent, ColdStart, Chromium script)" '[ -f $APP/main.py ] && [ -f $APP/setup_identity.py ] && [ -x $APP/launch_chromium.sh ] && [ -f $APP/identity_manager.py ]'
check "tests not copied to the Pi" '[ ! -e $APP/tests ] && [ ! -e $APP/run_tests.py ]'
check "config.py: LANGUAGE = \"es\"" 'grep -q "^LANGUAGE = \"es\"" $APP/config.py'
check "identity created (rpi-xxxxxxxx) and QR code" 'grep -q "\"raspberryId\": \"rpi-" $APP/identity.json && [ -f $APP/setup_qr_code.txt ]'
ID1="$(sed -n 's/.*"raspberryId": "\(rpi-[^"]*\)".*/\1/p' $APP/identity.json)"
check "summary: identifier + admin.js command" 'grep -q "node admin.js add $ID1" $T/out.txt'
CODE1="$(cd $REPO && "$REALPY" -c 'import json,sys; from device_code import device_code; print(device_code(json.load(open(sys.argv[1]))["deviceSecret"]))' "$(native $APP/identity.json)")"
check "summary: verification code + full add command" 'grep -q "node admin.js add $ID1 $CODE1" $T/out.txt && grep -q "Código de verificación       : $CODE1" $T/out.txt'
check "setup_qr_code.txt contains the code" 'grep -q "$CODE1" $APP/setup_qr_code.txt'
check "ringtone converted to .wav, used by default" '[ -f $APP/ringtone.wav ] && grep -q "^RINGTONE_PATH = str(BASE_DIR / \"ringtone.wav\")" $APP/config.py'
check "every .mp3 of the folder converted (ringtone of one's own)" '! for m in $APP/*.mp3; do [ -f "${m%.mp3}.wav" ] || echo missing; done | grep -q missing'
check "apt packages installed (cec-utils, ffmpeg...)" 'grep -q "apt-get install -y -q ffmpeg alsa-utils cec-utils python3-venv" $T/calls.log'
check "chromium installed if missing, never upgraded (--no-upgrade)" 'grep -q "apt-get install -y -q --no-upgrade chromium" $T/calls.log && ! grep -q "install -y -q ffmpeg.*chromium" $T/calls.log'
check "Python packages requested" 'grep -q "pip install -q websockets>=13,<18 evdev>=1.6,<3 gTTS>=2.5,<3 qrcode>=7,<9" $T/calls.log'
check "groups input,video,audio (missing render ignored)" 'grep -q "usermod -aG input,video,audio ofic" $T/calls.log'
check "agent service generated for the user ofic" 'grep -q "^User=ofic" $T/root/etc/systemd/system/tv-control.service && grep -q "ExecStart=$T/home/ofic/AppelerMamie/venv/bin/python3 -u $T/home/ofic/AppelerMamie/main.py" $T/root/etc/systemd/system/tv-control.service'
check "Chromium service generated, no YOUR_USER left" '! grep -q YOUR_USER $T/root/etc/systemd/system/*.service && grep -q "ExecStart=$T/home/ofic/AppelerMamie/launch_chromium.sh" $T/root/etc/systemd/system/chromium-autolaunch.service'
check "services enabled then restarted (no reboot asked)" 'grep -q "systemctl enable tv-control.service chromium-autolaunch.service" $T/calls.log && grep -q "systemctl restart" $T/calls.log && ! grep -q "^reboot" $T/calls.log'
check "Chromium camera/microphone policy: production + test server (:8443), valid JSON" '"$REALPY" -c "import json,sys; d=json.load(open(sys.argv[1])); u=[\"https://appelermami.fr\",\"https://appelermami.fr:8443\"]; sys.exit(0 if d[\"VideoCaptureAllowedUrls\"]==u and d[\"AudioCaptureAllowedUrls\"]==u else 1)" "$(native $T/root/etc/chromium/policies/managed/appelermamie.json)"'
check "installation log written" 'grep -q "INSTALACIÓN" $T/home/ofic/appelermamie-install.log'

check "config.py installed with HDMI_PORT = 3 by default" 'grep -q "^HDMI_PORT = 3$" $APP/config.py'
check "self-repair: step shown" 'grep -q "\[9/10\] Reparación automática" $T/out.txt'
check "self-repair: root copy of selfheal.py (outside ~/AppelerMamie)" 'cmp -s $T/root/usr/local/lib/appelermamie/selfheal.py $REPO/selfheal.py'
check "self-repair: service (user folder) and timer" 'grep -q "ExecStart=/usr/bin/python3 /usr/local/lib/appelermamie/selfheal.py $T/home/ofic/AppelerMamie$" $T/root/etc/systemd/system/appelermamie-selfheal.service && grep -q "OnUnitActiveSec=1min" $T/root/etc/systemd/system/appelermamie-selfheal.timer'
check "self-repair: timer enabled and started" 'grep -q "systemctl enable --now appelermamie-selfheal.timer" $T/calls.log'
check "agent: systemd watchdog (WatchdogSec)" 'grep -q "^WatchdogSec=120" $T/root/etc/systemd/system/tv-control.service'
check "hardware watchdog installed" 'grep -q "^RuntimeWatchdogSec=15s" $T/root/etc/systemd/system.conf.d/appelermamie-watchdog.conf'
check "Wi-Fi power saving off" 'grep -q "^wifi.powersave = 2" $T/root/etc/NetworkManager/conf.d/appelermamie-wifi.conf && grep -q "iw dev wlan0 set power_save off" $T/calls.log'
check "the TV does not turn on when the Pi starts (config.txt)" 'grep -q "^hdmi_ignore_cec_init=1$" $T/root/boot/firmware/config.txt && grep -q "^dtparam=audio=on$" $T/root/boot/firmware/config.txt'
check "config.py: nightly restart at 4 h by default" 'grep -q "^NIGHTLY_REBOOT_HOUR = 4$" $APP/config.py'

echo "=== 2. Update (run again, custom settings, restart accepted)"
sed -i -e 's|^MOUSE_DEVICE = None|MOUSE_DEVICE = "/dev/input/event4"|' -e 's|^AUDIO_DEVICE = None|AUDIO_DEVICE = "AUDIO"|' -e 's|^VOICE_VOLUME = 1.5|VOICE_VOLUME = 1.2|' -e 's|^SERVER_URL = "wss://appelermami.fr"|SERVER_URL = "wss://appelermami.fr:8443"|' -e 's|^HDMI_PORT = 3|HDMI_PORT = 2|' -e 's|^NIGHTLY_REBOOT_HOUR = 4|NIGHTLY_REBOOT_HOUR = None|' -e 's|^RINGTONE_PATH = .*|RINGTONE_PATH = str(BASE_DIR / "my-ringtone.wav")|' $APP/config.py
cp "$APP/ringtone.mp3" "$APP/my-ringtone.mp3"
printf 'x' >> $APP/main.py
: > $T/calls.log
run '\ns\n' "$T/src/Raspberry_receiver/install.sh"
check "the script ends without error" '[ "$(cat $T/rc.txt)" = 0 ]'
check "without --lang: language of the Pi kept by default (es)" 'grep -q "INSTALACIÓN" $T/out.txt && grep -q "^LANGUAGE = \"es\"" $APP/config.py'
check "same identity kept" 'grep -q "$ID1" $APP/identity.json && grep -q "Identidad existente conservada: $ID1" $T/out.txt'
check "custom HDMI_PORT (2) kept" 'grep -q "^HDMI_PORT = 2$" $APP/config.py'
check "ringtone of one's own: RINGTONE_PATH kept, its .mp3 converted" 'grep -q "^RINGTONE_PATH = str(BASE_DIR / \"my-ringtone.wav\")" $APP/config.py && [ -f $APP/my-ringtone.wav ]'
check "custom NIGHTLY_REBOOT_HOUR (None) kept" 'grep -q "^NIGHTLY_REBOOT_HOUR = None$" $APP/config.py'
check "config.txt: TV setting added only once" '[ "$(grep -c "^hdmi_ignore_cec_init=1$" $T/root/boot/firmware/config.txt)" = 1 ]'
check "custom AUDIO_DEVICE and VOICE_VOLUME kept" 'grep -q "^AUDIO_DEVICE = \"AUDIO\"" $APP/config.py && grep -q "^VOICE_VOLUME = 1.2" $APP/config.py'
check "MOUSE_DEVICE /dev/input/event4 replaced by automatic detection" 'grep -q "^MOUSE_DEVICE = None" $APP/config.py && grep -q "event4\" (ruta inestable)" $T/out.txt'
check "Pi on the test server: SERVER_URL kept, switch script installed" 'grep -q "^SERVER_URL = \"wss://appelermami.fr:8443\"" $APP/config.py && [ -x $APP/switch_server.sh ]'
check "test server: the Chromium policy keeps the domain without the port" 'grep -q "\"https://appelermami.fr\", \"https://appelermami.fr:8443\"" $T/root/etc/chromium/policies/managed/appelermamie.json'
check "copy of the old config.py kept" 'ls $APP/config.py.bak-* >/dev/null 2>&1 && grep -q "event4" $APP/config.py.bak-*'
check "program files updated" '! grep -q "x$" <(tail -c 2 $APP/main.py)'
check "restart done (answer \"s\")" 'grep -q "^reboot" $T/calls.log'

echo "=== 3. Run with sudo (root)"
fresh
printf '#!/bin/bash\n[ "$1" = "-u" ] && echo 0 || /usr/bin/id "$@"\n' > "$T/bin/id"; chmod +x "$T/bin/id"
run '' "$T/src/Raspberry_receiver/install.sh" --lang fr
rm "$T/bin/id"
check "refused with a clear message, nothing installed" '[ "$(cat $T/rc.txt)" != 0 ] && grep -q "Ne lancez pas ce script avec sudo" $T/out.txt && [ ! -d $APP ]'

echo "=== 4. Script run alone, without the project files"
fresh
mkdir -p "$T/src/alone"; cp "$T/src/Raspberry_receiver/install.sh" "$T/src/alone/"
run '' "$T/src/alone/install.sh"
check "refused with a message in 3 languages" '[ "$(cat $T/rc.txt)" != 0 ] && grep -q "Run this script from the Raspberry_receiver folder" $T/out.txt'

echo "=== 5. Files copied from Windows (CRLF line endings)"
fresh
sed -i 's/$/\r/' "$T/src/Raspberry_receiver/main.py" "$T/src/Raspberry_receiver/ColdStart/launch_chromium.sh"
run 'n\n' "$T/src/Raspberry_receiver/install.sh" --lang en
check "installed, line endings fixed" '[ "$(cat $T/rc.txt)" = 0 ] && ! grep -q $'"'"'\r'"'"' $APP/main.py $APP/launch_chromium.sh'
check "messages in English" 'grep -q "INSTALLING CALL GRANDMA" $T/out.txt'

echo "=== 5b. System without NetworkManager nor /boot/firmware/config.txt"
fresh
rm -rf "$T/root/etc/NetworkManager" "$T/root/boot"
run 'n\n' "$T/src/Raspberry_receiver/install.sh" --lang fr
check "installed without error, these settings simply skipped" '[ "$(cat $T/rc.txt)" = 0 ] && [ ! -e $T/root/etc/NetworkManager ] && [ ! -e $T/root/boot ] && grep -q "\[10/10\]" $T/out.txt'

echo "=== 6. A step fails (apt error)"
fresh
touch "$T/apt_fails"
run '' "$T/src/Raspberry_receiver/install.sh" --lang fr
check "stops, naming the step and the log" '[ "$(cat $T/rc.txt)" != 0 ] && grep -q "Échec pendant l.étape « Paquets système (quelques minutes) »" $T/out.txt && grep -q "appelermamie-install.log" $T/out.txt'
check "nothing else done after the failure" '[ ! -f $APP/identity.json ]'

echo "=== 7. Folder copied directly as ~/AppelerMamie"
fresh
cp -r "$T/src/Raspberry_receiver" "$APP"
run 'n\n' "$APP/install.sh" --lang fr
check "installed without error in the same folder" '[ "$(cat $T/rc.txt)" = 0 ] && [ -f $APP/identity.json ] && [ -f $APP/setup_identity.py ]'

echo "=== 8. File owned by another user (not writable)"
fresh
run 'n\n' "$T/src/Raspberry_receiver/install.sh" --lang es
chmod 444 "$APP/launch_chromium.sh"
: > $T/calls.log
run 'n\n' "$T/src/Raspberry_receiver/install.sh" --lang es
check "rights repaired with sudo, then installation finished" '[ "$(cat $T/rc.txt)" = 0 ] && grep -q "SUDO chown -R ofic: " $T/calls.log && [ -w "$APP/launch_chromium.sh" ]'

echo "=== 9. Installation stopped while copying: config.py intact"
fresh
run 'n\n' "$T/src/Raspberry_receiver/install.sh" --lang es
rm -f "$APP/start_tv_control.sh"; mkdir "$APP/start_tv_control.sh"
run '' "$T/src/Raspberry_receiver/install.sh"
check "stops while copying the files" '[ "$(cat $T/rc.txt)" != 0 ] && grep -q "Fallo durante el paso «Archivos" $T/out.txt'
check "config.py keeps the language (es), no temporary file left" 'grep -q "^LANGUAGE = \"es\"" $APP/config.py'
rm -rf "$APP/start_tv_control.sh"
run '\nn\n' "$T/src/Raspberry_receiver/install.sh"
check "run again without --lang: takes es again and finishes" '[ "$(cat $T/rc.txt)" = 0 ] && grep -q "^LANGUAGE = \"es\"" $APP/config.py && [ ! -f $APP/.config.py.new ]'

echo "=== 10. Old config.py without HDMI_PORT (previous version)"
fresh
run 'n\n' "$T/src/Raspberry_receiver/install.sh" --lang es
sed -i -e '/^HDMI_PORT = /d' -e 's|^AUDIO_DEVICE = None|AUDIO_DEVICE = "AUDIO"|' $APP/config.py
run 'n\n' "$T/src/Raspberry_receiver/install.sh" --lang es
check "update: HDMI_PORT = 3 added, other settings kept" '[ "$(cat $T/rc.txt)" = 0 ] && [ "$(grep -c "^HDMI_PORT = 3$" $APP/config.py)" = 1 ] && grep -q "^AUDIO_DEVICE = \"AUDIO\"" $APP/config.py'

echo
echo "$pass passed, $fail failed"
[ "$fail" = 0 ]
