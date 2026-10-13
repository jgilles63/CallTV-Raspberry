# Agent of the calling TV (B.9): outgoing_call_start turns the TV on without
# ringtone, the end of this call gives the TV back, the call is told when the
# agent reconnects (B.7), the mouse does not hang up, received calls unchanged.
import asyncio
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Raspberry_receiver/

cfg = types.ModuleType("config")
cfg.LANGUAGE = "fr"; cfg.RASPBERRY_ID = "rpi-mytv"; cfg.DEVICE_SECRET = "secret"
cfg.SERVER_URL = "wss://x"; cfg.UNAUTHORIZED_RETRY_DELAY = 30; cfg.CALL_DURATION = 30
cfg.MOUSE_DEVICE = None; cfg.MOUSE_RETRY_DELAY = 5
sys.modules["config"] = cfg

tv_calls = []
sounds = []
tv = types.ModuleType("tv_control")
tv.tv_on_and_accept = lambda: tv_calls.append("on")
tv.tv_return = lambda: tv_calls.append("return")
sys.modules["tv_control"] = tv


class FakeSound:
    def play(self, name):
        sounds.append(("play", name))

    def stop(self):
        sounds.append(("stop",))


audio = types.ModuleType("tts_audio")
audio.AlertSound = FakeSound
sys.modules["tts_audio"] = audio
evdev = types.ModuleType("evdev")
evdev.InputDevice = evdev.ecodes = evdev.list_devices = None
sys.modules["evdev"] = evdev

import agent  # noqa: E402

passed = failed = 0


def check(label, condition, detail=""):
    global passed, failed
    passed, failed = passed + bool(condition), failed + (not condition)
    print(f"{'OK ' if condition else 'KO '} {label} {detail}")


async def main():
    a = agent.TVControlAgent()
    sent = []

    async def capture(data):
        sent.append(data)

    a.send_message = capture

    await a.register_device()
    check("registration without call: activeCallId empty", sent[-1].get("activeCallId") is None)

    await a.handle_message({"type": "outgoing_call_start", "callId": "tv-1", "targetDeviceId": "rpi-mamie"})
    check("outgoing_call_start: the TV is turned on", tv_calls == ["on"], tv_calls)
    check("no ringtone for a call made from this TV", sounds == [], sounds)
    check("call remembered", a.outgoing_call_id == "tv-1")

    await a.register_device()
    check("reconnection: the call made from this TV is told (B.7)", sent[-1].get("activeCallId") == "tv-1")

    sent.clear()
    await a.on_mouse_click_async()
    check("mouse click during the call: nothing sent (the phone hangs up)", sent == [], sent)

    await a.handle_message({"type": "hangup", "callId": "other"})
    check("hangup of another call: TV not given back", tv_calls == ["on"])
    await a.handle_message({"type": "hangup", "callId": "tv-1"})
    check("end of the call made from this TV: the TV is given back", tv_calls == ["on", "return"], tv_calls)
    check("call forgotten", a.outgoing_call_id is None)

    await a.handle_message({"type": "outgoing_call_start"})
    check("without callId: ignored", tv_calls == ["on", "return"] and a.outgoing_call_id is None)

    # Received call (unchanged): ringing window then hangup from the caller
    tv_calls.clear()
    sounds.clear()
    a.current_call_id = "in-1"
    a.call_window = True
    await a.handle_message({"type": "hangup", "callId": "in-1"})
    check("received call hung up while ringing: TV given back, ringtone stopped",
          tv_calls == ["return"] and ("stop",) in sounds and a.current_call_id is None)


asyncio.run(main())
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
