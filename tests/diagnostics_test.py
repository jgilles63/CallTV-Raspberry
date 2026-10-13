# Health report of the Raspberry (diagnostics.py) and its request by the
# server (agent.py: diagnose_request -> diagnose_report). The system files and
# commands of the Pi are simulated.
import asyncio
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Raspberry_receiver/

cfg = types.ModuleType("config")
cfg.LANGUAGE = "fr"; cfg.RASPBERRY_ID = "rpi-diag"; cfg.DEVICE_SECRET = "TOP-SECRET-VALUE"
cfg.SERVER_URL = "wss://127.0.0.1:1"; cfg.UNAUTHORIZED_RETRY_DELAY = 30; cfg.CALL_DURATION = 30
cfg.MOUSE_DEVICE = None; cfg.MOUSE_RETRY_DELAY = 5; cfg.HDMI_PORT = 3
cfg.BASE_DIR = Path(".")
sys.modules["config"] = cfg

tv = types.ModuleType("tv_control")
tv.tv_on_and_accept = tv.tv_return = lambda: None
sys.modules["tv_control"] = tv
audio = types.ModuleType("tts_audio")
audio.AlertSound = lambda: types.SimpleNamespace(play=lambda n: None, stop=lambda: None)
audio.find_ringing_card = lambda: {"name": "USB  Speaker", "id": "AUDIO"}
sys.modules["tts_audio"] = audio
evdev = types.ModuleType("evdev")
evdev.InputDevice = evdev.ecodes = evdev.list_devices = None
sys.modules["evdev"] = evdev

import diagnostics as d  # noqa: E402
import agent  # noqa: E402

passed = failed = 0


def check(label, condition, detail=""):
    global passed, failed
    passed, failed = passed + bool(condition), failed + (not condition)
    print(f"{'OK ' if condition else 'KO '} {label} {detail}")


# ---------------- simulated system ----------------
FILES = {
    "/proc/device-tree/model": "Raspberry Pi 5 Model B Rev 1.0\x00",
    "/etc/os-release": 'PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"\nNAME="Debian"\n',
    "/proc/uptime": "277260.5 1000.0\n",
    "/sys/class/net/eth0/operstate": "down\n",
    "/sys/class/net/wlan0/operstate": "up\n",
    "/sys/class/net/lo/operstate": "unknown\n",
    "/proc/net/wireless": "Inter-| sta-|   Quality        |\n face | tus | link level noise\n wlan0: 0000   45.  -72.  -256        0      0\n",
    "/sys/class/drm/card1-HDMI-A-1/status": "connected\n",
    "/sys/class/drm/card1-HDMI-A-2/status": "disconnected\n",
    "/sys/class/video4linux/video0/name": "HD Pro Webcam C920\n",
    "/sys/class/video4linux/video1/name": "Trust 1080p Full HD Webcam: Tru\n",
    "/sys/class/video4linux/video19/name": "pispbe-output0\n",
    "/proc/asound/cards": " 0 [vc4hdmi0      ]: vc4-hdmi - vc4-hdmi-0\n                      vc4-hdmi-0\n 2 [C920           ]: USB-Audio - HD Pro Webcam C920\n                      HD Pro Webcam C920 at usb\n",
    "/proc/bus/input/devices": 'I: Bus=0003\nN: Name="Logitech USB Optical Mouse"\nH: Handlers=mouse0 event3\n\nI: Bus=0019\nN: Name="vc4-hdmi-0"\nH: Handlers=kbd event0\n',
    "/proc/meminfo": "MemTotal:        8000000 kB\nMemAvailable:    6000000 kB\n",
    "/sys/class/thermal/thermal_zone0/temp": "72350\n",
    "/var/lib/appelermamie/selfheal.json": json.dumps({"history": [
        {"time": 1760000000, "action": "page", "reason": "page not connected"},
        {"time": 1760241600, "action": "reboot", "reason": "nightly"}]}),
}
GLOBS = {
    "/sys/class/net/*/operstate": ["/sys/class/net/eth0/operstate", "/sys/class/net/lo/operstate", "/sys/class/net/wlan0/operstate"],
    "/sys/class/drm/*HDMI*/status": ["/sys/class/drm/card1-HDMI-A-1/status", "/sys/class/drm/card1-HDMI-A-2/status"],
    "/sys/class/video4linux/video*": ["/sys/class/video4linux/video0", "/sys/class/video4linux/video1", "/sys/class/video4linux/video19"],
    "/proc/asound/card2/pcm*c": ["/proc/asound/card2/pcm0c"],
}
DRIVERS = {"/sys/class/video4linux/video0/device/driver": "/drivers/uvcvideo",
           "/sys/class/video4linux/video1/device/driver": "/drivers/uvcvideo",
           "/sys/class/video4linux/video19/device/driver": "/drivers/pispbe"}
COMMANDS = {
    "systemctl is-active tv-control.service": "active\n",
    "systemctl is-active chromium-autolaunch.service": "failed\n",
    "chromium --version": "Chromium 140.0.7339.185 built on Debian\n",
    'echo "pow 0" | cec-client -s -d 1': "opening a connection...\npower status: standby\n",
    "vcgencmd get_throttled": "throttled=0x50005\n",
    "systemctl is-active appelermamie-selfheal.timer": "active\n",
    "systemctl show -p RuntimeWatchdogUSec": "RuntimeWatchdogUSec=15s\n",
    "iw dev wlan0 get power_save": "Power save: on\n",
    "journalctl -u appelermamie-selfheal.service -n 500 --no-pager -o short-iso":
        "2026-10-12 python3[9]: ⚠️ Self-repair: network (wifi)\n",
    "journalctl -u tv-control.service -n 500 --no-pager -o short-iso":
        "".join(f"2026-10-12 agent[1]: 📨 Message received {i}\n" for i in range(30)) +
        "".join(f"2026-10-12 agent[1]: ❌ Send error {i} " + "x" * 300 + "\n" for i in range(20)),
    "journalctl -u chromium-autolaunch.service -n 500 --no-pager -o short-iso": "2026-10-12 chromium: started\n"
        "2026-10-11 launch_chromium.sh[1]: [1:1:1011/172518.653013:ERROR:dbus/object_proxy.cc:572] Failed to call method\n"
        "2026-10-11 launch_chromium.sh[1]: [1:2:1011/172518.701018:ERROR:dbus/bus.cc:405] Failed to connect to the bus: x\n"
        "2026-10-11 launch_chromium.sh[1]: [1:3:1011/172521.828608:ERROR:google_apis/gcm/engine/registration_request.cc:291] DEP\n"
        "2026-10-11 launch_chromium.sh[1]: [1:1:1011/172523.068982:ERROR:ui/gl/gl_surface_presentation_helper.cc:260] VSync\n"
        "2026-10-11 launch_chromium.sh[1]: NotReadableError: Could not start video source\n",
}
commands_run = []


def fake_run(command, timeout=d.COMMAND_TIMEOUT, shell=False):
    key = command if shell else " ".join(command)
    commands_run.append(key)
    return COMMANDS.get(key)


d.read_file = FILES.get
d.run = fake_run
d.glob.glob = lambda pattern: GLOBS.get(pattern, [])
d.os.path.realpath = lambda p: DRIVERS.get(p, p)
d.os.path.isdir = lambda p: False


class FakeSocket:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


d.socket.create_connection = lambda address, timeout: FakeSocket()

report = d.run_checks()
by_id = {c["id"]: c for c in report["checks"]}
print(json.dumps(by_id, ensure_ascii=False, indent=1)[:3000])

check("report version and time", report["version"] == 1 and report["time"].endswith("+00:00"))
check("model (NUL stripped)", by_id["system.model"]["value"] == "Raspberry Pi 5 Model B Rev 1.0")
check("OS name", by_id["system.os"]["value"].startswith("Debian GNU/Linux 12 (bookworm) — Linux "))
check("uptime 3d 05:01", by_id["system.uptime"]["value"] == "3d 05:01")
check("services: active ok, failed fail",
      by_id["service.tvControl"]["status"] == "ok" and by_id["service.chromium"] == {"id": "service.chromium", "status": "fail", "value": "failed"})
check("chromium version", by_id["version.chromium"]["value"] == "Chromium 140.0.7339.185 built on Debian")
check("server reachable", by_id["network.server"] == {"id": "network.server", "status": "ok", "value": "wss://127.0.0.1:1"})
check("interfaces up (no lo)", by_id["network.interfaces"]["value"] == "wlan0")
check("wifi -72 dBm: warn", by_id["network.wifi"] == {"id": "network.wifi", "status": "warn", "value": "wlan0 -72 dBm"})
check("hdmi: one connected", by_id["hdmi"]["status"] == "ok" and by_id["hdmi"]["value"] == "HDMI-A-1: connected, HDMI-A-2: disconnected")
check("cec standby: warn, with HDMI_PORT", by_id["cec"] == {"id": "cec", "status": "warn", "value": "standby (HDMI_PORT=3)"})
check("cameras: USB webcams only, name cut by the kernel cleaned",
      by_id["camera"] == {"id": "camera", "status": "ok", "value": "HD Pro Webcam C920, Trust 1080p Full HD Webcam"})
check("microphone: capture card only", by_id["microphone"]["value"] == "HD Pro Webcam C920" and by_id["microphone"]["status"] == "ok")
check("speaker (double space removed)", by_id["speaker"] == {"id": "speaker", "status": "ok", "value": "USB Speaker (AUDIO)"})
check("mouse: pointer only", by_id["mouse"] == {"id": "mouse", "status": "ok", "value": "Logitech USB Optical Mouse"})
check("memory 75 %", by_id["memory"]["status"] == "ok" and "(75%)" in by_id["memory"]["value"])
check("temperature 72.3 °C: warn", by_id["temperature"] == {"id": "temperature", "status": "warn", "value": "72.3 °C"})
check("power 0x50005: fail, flags decoded",
      by_id["power"]["status"] == "fail" and by_id["power"]["value"] == "0x50005 now:underVoltage now:throttled boot:underVoltage boot:throttled")
logs = report["logs"]["tv-control.service"]
check("logs: only error lines, the last 15, shortened",
      len(logs) == 15 and all("❌" in line for line in logs) and logs[-1].startswith("2026-10-12 agent[1]: ❌ Send error 19")
      and max(map(len, logs)) == 200)
check("Chromium noise (dbus, gcm, vsync) left out, real errors kept",
      [line[-36:] for line in report["logs"]["chromium-autolaunch.service"]] == ["eError: Could not start video source"])
check("no secret in the report", "TOP-SECRET-VALUE" not in json.dumps(report))
check("disk check present (crash-proof)", "disk" in by_id)
check("self-repair: active, last action, number of actions",
      by_id["selfheal"]["status"] == "ok" and by_id["selfheal"]["value"].startswith("active, 2025-10-12 ")
      and by_id["selfheal"]["value"].endswith(" reboot (nightly), 2"), by_id["selfheal"]["value"])
check("hardware watchdog 15s: ok", by_id["system.watchdog"] == {"id": "system.watchdog", "status": "ok", "value": "15s"})
check("Wi-Fi power saving on: warn", by_id["network.powersave"] == {"id": "network.powersave", "status": "warn", "value": "on"})
check("self-repair actions in the logs", report["logs"]["appelermamie-selfheal.service"] == ["2026-10-12 python3[9]: ⚠️ Self-repair: network (wifi)"])
COMMANDS["systemctl is-active appelermamie-selfheal.timer"] = "inactive\n"
FILES["/var/lib/appelermamie/selfheal.json"] = None
check("self-repair not installed: warn", d.check_selfheal() == {"id": "selfheal", "status": "warn", "value": "inactive"})
COMMANDS["systemctl show -p RuntimeWatchdogUSec"] = "RuntimeWatchdogUSec=0\n"
check("no hardware watchdog: warn", d.check_watchdog()["status"] == "warn")
COMMANDS["iw dev wlan0 get power_save"] = "Power save: off\n"
check("Wi-Fi power saving off: ok", d.check_wifi_powersave()["status"] == "ok")
del COMMANDS["iw dev wlan0 get power_save"]
check("no Wi-Fi (iw missing): info", d.check_wifi_powersave()["status"] == "info")

# --- states that fail ---
FILES["/sys/class/drm/card1-HDMI-A-1/status"] = "disconnected\n"
check("no HDMI connected: fail", d.check_hdmi()["status"] == "fail")
COMMANDS['echo "pow 0" | cec-client -s -d 1'] = "opening...\nERROR: could not open a connection\n"
check("CEC without answer: fail", d.check_cec() == {"id": "cec", "status": "fail", "value": "no answer"})
COMMANDS['echo "pow 0" | cec-client -s -d 1'] = "power status: on\n"
del cfg.HDMI_PORT
check("config.py without HDMI_PORT (older): fail, told",
      d.check_cec() == {"id": "cec", "status": "fail", "value": "on (HDMI_PORT missing in config.py)"})
cfg.HDMI_PORT = 3
check("TV on: ok", d.check_cec() == {"id": "cec", "status": "ok", "value": "on (HDMI_PORT=3)"})
commands_run.clear()
check("CEC skipped during a call (cec-client not run)",
      d.check_cec(skip=True)["value"] == "skipped" and not any("cec-client" in c for c in commands_run))
COMMANDS["vcgencmd get_throttled"] = "throttled=0x0\n"
check("power 0x0: ok", d.check_power() == {"id": "power", "status": "ok", "value": "0x0"})
check("power since boot only: warn", (COMMANDS.__setitem__("vcgencmd get_throttled", "throttled=0x10000\n"), d.check_power()["status"])[1] == "warn")


def refused(address, timeout):
    raise ConnectionRefusedError()


d.socket.create_connection = refused
check("server unreachable: fail with the reason", d.check_server()["value"] == "wss://127.0.0.1:1 (ConnectionRefusedError)")
check("a crashing check does not stop the others",
      d.safe(lambda: 1 / 0)["status"] == "fail")
check("check_services crashing still gives a list entry", isinstance(d.run_checks()["checks"], list))

# --- text in French ---
text = d.format_report(report)
print(text)
check("French title", text.startswith("🩺 État des lieux du Raspberry rpi-diag ("))
check("French labels with icons",
      "⚠️ Signal Wi-Fi : wlan0 -72 dBm" in text and "❌ Service de l'écran (chromium-autolaunch) : failed" in text)
check("power flags translated",
      "❌ Alimentation : 0x50005 tension trop faible (maintenant) ralenti (maintenant) tension trop faible (depuis le démarrage)" in text)
check("logs title", "Dernières erreurs de chromium-autolaunch.service :\n  2026-10-11" in text)
check("no errors: (aucune)",
      d.format_report({"checks": [], "logs": {"x.service": []}}).endswith("Dernières erreurs de x.service :\n  (aucune)"))


# --- agent: diagnose_request ---
async def agent_test():
    a = agent.TVControlAgent()
    sent = []

    async def capture(data):
        sent.append(data)

    a.send_message = capture
    calls = []
    d.run_checks = lambda skip_cec=False: (calls.append(skip_cec), {"version": 1, "checks": []})[1]
    await a.handle_message({"type": "diagnose_request", "requestId": "req-1"})
    for _ in range(50):
        if sent:
            break
        await asyncio.sleep(0.02)
    check("agent answers diagnose_report with the requestId",
          sent == [{"type": "diagnose_report", "requestId": "req-1", "report": {"version": 1, "checks": []}}])
    check("outside a call: CEC checked", calls == [False])

    sent.clear()
    a.outgoing_call_id = "call-9"
    await a.handle_message({"type": "diagnose_request", "requestId": "req-2"})
    for _ in range(50):
        if sent:
            break
        await asyncio.sleep(0.02)
    check("during a call: CEC skipped", calls == [False, True] and sent[0]["requestId"] == "req-2")

    def crash(skip_cec=False):
        raise RuntimeError("disk on fire")

    d.run_checks = crash
    sent.clear()
    await a.handle_message({"type": "diagnose_request", "requestId": "req-3"})
    for _ in range(50):
        if sent:
            break
        await asyncio.sleep(0.02)
    check("checks crash: an error report is still sent",
          sent == [{"type": "diagnose_report", "requestId": "req-3", "report": {"version": 1, "error": "disk on fire"}}])


asyncio.run(agent_test())
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
