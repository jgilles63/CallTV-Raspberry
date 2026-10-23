# Output of the call sound (call_audio.py): TV (HDMI) when a TV answers CEC and
# accepts sound, USB speaker otherwise. PipeWire (pw-dump, wpctl) and the ELD
# files of /proc/asound are simulated, from the states seen on real Pis
# (15/10/2026): HDMI profile left "off" after a boot with the TV in standby,
# computer monitor whose ELD announces sound.
import copy
import json
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Raspberry_receiver/

cfg = types.ModuleType("config")
cfg.BASE_DIR = Path(tempfile.gettempdir())
sys.modules["config"] = cfg

ringing_card = {"value": {"index": 3, "id": "AUDIO", "driver": "USB-Audio", "playback": True}}
audio = types.ModuleType("tts_audio")
audio.find_ringing_card = lambda: ringing_card["value"]
sys.modules["tts_audio"] = audio

import call_audio  # noqa: E402

passed = failed = 0


def check(label, condition, detail=""):
    global passed, failed
    passed, failed = passed + bool(condition), failed + (not condition)
    print(f"{'OK ' if condition else 'KO '} {label} {detail}")


HDMI_PROFILES = [
    {"index": 0, "name": "off", "available": "yes"},
    {"index": 1, "name": "output:hdmi-stereo", "available": "yes"},
    {"index": 2, "name": "output:hdmi-surround", "available": "yes"},
]


def device(dev_id, card, profile="off"):
    return {"id": dev_id, "type": "PipeWire:Interface:Device",
            "info": {"props": {"api.alsa.card": card, "device.name": f"alsa_card.{card}"},
                     "params": {"EnumProfile": HDMI_PROFILES if card in ("0", "1") else [],
                                "Profile": [{"name": profile}]}}}


def sink(node_id, dev_id, name, description):
    return {"id": node_id, "type": "PipeWire:Interface:Node",
            "info": {"props": {"media.class": "Audio/Sink", "device.id": dev_id,
                               "node.name": name, "node.description": description}}}


def default_meta(name):
    # As in pw-dump: the props of a metadata object are at its top level (seen on a Pi, v0.2.3)
    return {"id": 30, "type": "PipeWire:Interface:Metadata", "props": {"metadata.name": "default"},
            "metadata": [{"subject": 0, "key": "default.configured.audio.sink", "value": {"name": "x"}},
                         {"subject": 0, "key": "default.audio.sink", "value": {"name": name}}]}


USB = sink(59, 48, "alsa_output.usb-AUDIO.analog-stereo", "USB  AUDIO Analog Stereo")
HDMI = sink(84, 51, "alsa_output.platform-fef00700.hdmi.hdmi-stereo", "Built-in Audio Digital Stereo (HDMI)")


def tv_pi_after_boot():
    """Pi of the TV after a boot with the TV in standby: HDMI profile "off", no HDMI sink."""
    return [device(48, 3), device(51, "0"), device(52, "1"), USB, default_meta(USB["info"]["props"]["node.name"])]


class FakePipeWire:
    def __init__(self, objects, reachable=True):
        self.objects = copy.deepcopy(objects)
        self.reachable = reachable
        self.commands = []

    def run(self, command):
        self.commands.append(command)
        if not self.reachable:
            return None
        if command == ["pw-dump"]:
            return json.dumps(self.objects)
        if command[:2] == ["wpctl", "set-profile"]:
            # The HDMI sink appears once its output profile is chosen
            if command[2] == "51" and command[3] in ("1", "2") and not any(o["id"] == 84 for o in self.objects):
                self.objects.append(copy.deepcopy(HDMI))
            return ""
        if command[:2] == ["wpctl", "set-default"]:
            return ""
        return None

    def defaults(self):
        return [c[2] for c in self.commands if c[:2] == ["wpctl", "set-default"]]

    def profiles(self):
        return [c[2:] for c in self.commands if c[:2] == ["wpctl", "set-profile"]]


ELD_TV = "monitor_name\t\tHISENSE\nconnection_type\t\tHDMI\neld_version\t\t[0x2] CEA-861D or below\nsad_count\t\t3\n"
ELD_MONITOR = "monitor_name\t\tKA242Y\nconnection_type\t\tHDMI\neld_version\t\t[0x2] CEA-861D or below\nsad_count\t\t1\n"
ELD_EMPTY = "monitor_name\t\t\nconnection_type\t\tHDMI\neld_version\t\t[0x0] reserved\n"


def asound(card0_eld, card1_eld=ELD_EMPTY):
    """Fake /proc/asound: card0 = HDMI 0 (the TV), card1 = HDMI 1 (second screen, nothing plugged by default)."""
    root = tempfile.mkdtemp()
    for card, text in (("0", card0_eld), ("1", card1_eld)):
        os.makedirs(os.path.join(root, f"card{card}"))
        with open(os.path.join(root, f"card{card}", "eld#0"), "w", encoding="utf-8") as f:
            f.write(text)
        with open(os.path.join(root, f"card{card}", "id"), "w", encoding="utf-8") as f:
            f.write(f"vc4hdmi{card}\n")
    return os.path.join(root, "card*", "eld#*")


def route(objects, eld, tv_present, mode="auto", reachable=True):
    pw = FakePipeWire(objects, reachable)
    call_audio.run = pw.run
    call_audio.ELD_GLOB = asound(eld)
    cfg.CALL_AUDIO_OUTPUT = mode
    result = call_audio.route_call_audio(tv_present)
    return result, pw


call_audio.HDMI_ATTEMPTS = 3

# --- Second screen on HDMI 1 (PLAN_SECOND_ECRAN.md): never its sound ---
import display_mode  # noqa: E402
display_mode.second_screen = lambda: (1024, 600)
call_audio.ELD_GLOB = asound(ELD_TV, ELD_MONITOR)
check("TV + second screen with sound: only the card of the TV (vc4hdmi0)", call_audio.hdmi_cards_with_sound() == ["0"],
      call_audio.hdmi_cards_with_sound())
display_mode.second_screen = lambda: None
call_audio.ELD_GLOB = asound(ELD_EMPTY, ELD_MONITOR)
check("one screen on HDMI 1 only (no second screen): its sound used as before", call_audio.hdmi_cards_with_sound() == ["1"])
display_mode.second_screen = lambda: (1024, 600)
check("second screen plugged, TV still waking up (no sound yet): never the second screen, nothing yet (review of 23/10/2026)",
      call_audio.hdmi_cards_with_sound() == [], call_audio.hdmi_cards_with_sound())
call_audio.ELD_GLOB = asound(ELD_TV, ELD_MONITOR)
check("second screen plugged, TV awake: the TV", call_audio.hdmi_cards_with_sound() == ["0"])
display_mode.second_screen = lambda: None
call_audio.ELD_GLOB = asound(ELD_TV)
check("TV alone: as before", call_audio.hdmi_cards_with_sound() == ["0"])
pw = FakePipeWire(tv_pi_after_boot() + [copy.deepcopy(HDMI)], True)
call_audio.run = pw.run
call_audio.ELD_GLOB = asound(ELD_TV, ELD_MONITOR)
check("tv_hdmi_as_default (ringtone without USB speaker): HDMI of the TV made the default output",
      call_audio.tv_hdmi_as_default() is True and pw.defaults() == ["84"], pw.commands)
pw = FakePipeWire([], False)
call_audio.run = pw.run
check("tv_hdmi_as_default without PipeWire: False, no crash", call_audio.tv_hdmi_as_default() is False)
call_audio.time.sleep = lambda s: None

# --- The TV of the real Pi: HDMI output left "off" at boot ---
result, pw = route(tv_pi_after_boot(), ELD_TV, tv_present=True)
check("TV answering CEC: call sound on the TV", result == "hdmi", result)
check("HDMI output turned back on with the stereo profile", pw.profiles() == [["51", "1"]], pw.profiles())
check("HDMI output becomes the default output", pw.defaults() == ["84"], pw.defaults())
check("last route remembered for the health report", call_audio.last_route == "hdmi")

objects = tv_pi_after_boot() + [copy.deepcopy(HDMI)]
result, pw = route(objects, ELD_TV, tv_present=True)
check("HDMI output already on: no profile change", result == "hdmi" and pw.profiles() == [], pw.commands)

# --- Computer monitor: its ELD announces sound, but no CEC ---
objects = tv_pi_after_boot() + [copy.deepcopy(HDMI)]
result, pw = route(objects, ELD_MONITOR, tv_present=False)
check("monitor without CEC: call sound on the USB speaker", result == "usb", result)
check("monitor: the USB speaker becomes the default output", pw.defaults() == ["59"], pw.defaults())
check("monitor: HDMI output not touched", pw.profiles() == [], pw.profiles())

# --- TV answering CEC but without sound on HDMI (empty ELD) ---
result, pw = route(tv_pi_after_boot(), ELD_EMPTY, tv_present=True)
check("TV without HDMI sound: back to the USB speaker", result == "usb" and pw.defaults() == ["59"], pw.commands)

# --- TV, but the HDMI profile does not bring a sink (PipeWire refuses) ---
objects = tv_pi_after_boot()
objects[1]["info"]["params"]["EnumProfile"] = [{"index": 0, "name": "off", "available": "yes"},
                                               {"index": 5, "name": "output:hdmi-stereo", "available": "yes"}]
result, pw = route(objects, ELD_TV, tv_present=True)
check("HDMI sink never appearing: USB speaker after the wait", result == "usb" and pw.defaults() == ["59"],
      pw.commands)

# --- Profile choice: an available profile first, stereo first ---
dev = device(51, "0")
dev["info"]["params"]["EnumProfile"] = [
    {"index": 1, "name": "output:hdmi-stereo", "available": "no"},
    {"index": 2, "name": "output:hdmi-surround", "available": "yes"},
    {"index": 3, "name": "output:hdmi-stereo-extra1", "available": "yes"},
]
check("unavailable stereo profile: an available HDMI profile is used",
      call_audio.hdmi_profile(dev)["index"] in (2, 3), call_audio.hdmi_profile(dev))
dev["info"]["params"]["EnumProfile"] = [{"index": 1, "name": "output:hdmi-stereo", "available": "no"}]
check("only an \"unavailable\" HDMI profile: still tried (the ELD said yes)",
      call_audio.hdmi_profile(dev)["index"] == 1)
check("device without HDMI profile: none", call_audio.hdmi_profile(device(48, 3)) is None)

# --- Forced choices (config.CALL_AUDIO_OUTPUT) ---
result, pw = route(tv_pi_after_boot(), ELD_TV, tv_present=True, mode="usb")
check("CALL_AUDIO_OUTPUT=\"usb\": USB speaker even with a TV", result == "usb" and pw.profiles() == [], pw.commands)
result, pw = route(tv_pi_after_boot(), ELD_TV, tv_present=False, mode="hdmi")
check("CALL_AUDIO_OUTPUT=\"hdmi\": TV even without a CEC answer", result == "hdmi" and pw.defaults() == ["84"],
      pw.commands)
result, pw = route(tv_pi_after_boot(), ELD_TV, tv_present=True, mode=None)
check("CALL_AUDIO_OUTPUT empty: automatic", result == "hdmi", result)

# --- Without USB speaker, PipeWire unreachable ---
ringing_card["value"] = None
result, pw = route(tv_pi_after_boot(), ELD_MONITOR, tv_present=False)
check("no USB speaker and no TV: default output unchanged", result is None and pw.defaults() == [], pw.commands)
ringing_card["value"] = {"index": 3, "id": "AUDIO", "driver": "USB-Audio", "playback": True}
result, pw = route(tv_pi_after_boot(), ELD_TV, tv_present=True, reachable=False)
check("PipeWire unreachable: no crash, nothing chosen", result is None, result)

# --- Default output shown in the health report ---
pw = FakePipeWire(tv_pi_after_boot())
call_audio.run = pw.run
check("default output: its description", call_audio.default_sink_name() == "USB  AUDIO Analog Stereo",
      call_audio.default_sink_name())
call_audio.run = FakePipeWire([], reachable=False).run
check("default output unknown: None", call_audio.default_sink_name() is None)

# --- Environment of the commands (system service, no XDG_RUNTIME_DIR) ---
saved = os.environ.pop("XDG_RUNTIME_DIR", None)
env = call_audio.pipewire_env()
check("XDG_RUNTIME_DIR added for PipeWire", env.get("XDG_RUNTIME_DIR", "").startswith("/run/user/"),
      env.get("XDG_RUNTIME_DIR"))
os.environ["XDG_RUNTIME_DIR"] = "/run/user/1234"
check("XDG_RUNTIME_DIR already set: kept", call_audio.pipewire_env()["XDG_RUNTIME_DIR"] == "/run/user/1234")
if saved is None:
    os.environ.pop("XDG_RUNTIME_DIR", None)
else:
    os.environ["XDG_RUNTIME_DIR"] = saved

# --- The default config.py ---
real_config = (Path(__file__).resolve().parents[1] / "config.py").read_text(encoding="utf-8")
check("config.py: CALL_AUDIO_OUTPUT = \"auto\" by default", '\nCALL_AUDIO_OUTPUT = "auto"\n' in real_config)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
