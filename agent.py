#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Main agent:
- handles the WebSocket connection to the signaling server;
- receives the calls;
- detects mouse clicks with evdev;
- accepts a call when SIGUSR1 is received;
- listens to the remote control of the TV (HDMI-CEC, remote_keys.py): OK
  answers and Back declines while it rings, Back hangs up during a received
  call, otherwise the keys go to the TV page (remote_key, its menu);
- listens to the volume of the microphone outside calls (sound_level.py):
  the robot of the TV page reacts when someone speaks (sound_activity);
- understands the spoken commands to the robot (voice_commands.py): "Robot
  bonjour", "Robot, quelle heure est-il ?", "Robot, quel temps fait-il ?",
  "Robot, comment ça va ?" (health report said, diagnostics.py) ->
  the robot of the TV page moves (voice_command) and answers on the speaker
  (robot_answers.py; the weather is asked to the server); "Robot, mets la
  radio" / "radio 101.2" / "stop" (radio.py, radio_state for the TV page),
  "Robot, volume 5", "Robot, appelle <TV contact>" (tv_call_request: the
  call starts from this TV; contacts asked with tv_contacts_request);
- settings page of the TV (settings_request / settings_apply): language,
  ringtone volume, place of the weather saved in settings.json
  (settings_store.py), speech model of a new language downloaded
  (voice_model.py), then the agent restarts itself if needed;
- calendar of the TV (calendar_request / calendar_save / calendar_delete):
  notes kept on the Raspberry only, in calendar.json (calendar_store.py);
- sends a periodic heartbeat;
- sends its health report when the server asks for it (diagnostics.py);
- tells systemd it is alive and writes its state for the self-repair
  (selfheal.py) every 30 s.
"""

import asyncio
import datetime
import json
import os
import re
import signal
import socket
import threading
import time

import websockets
from evdev import InputDevice, ecodes, list_devices

import calendar_store
import config
import diagnostics
import display_mode
import radio
import remote_keys
import settings_store
import sound_level
import robot_answers
import tts_audio
import tv_control
import voice_commands
import voice_model
from device_code import device_code
from i18n import t
from tts_audio import AlertSound
from tv_control import tv_on_and_accept, tv_return

# Spoken commands: at most one every this many seconds
VOICE_COMMAND_INTERVAL = 4
# Spoken commands while it rings: answer or decline the call (the others are
# ignored then; these two only then)
RINGING_COMMANDS = ("answer", "decline")
# Spoken commands answered (fixed sentence of i18n.py, or None: made at each answer)
VOICE_ANSWERS = {"hello": "voice.hello", "time": None, "weather": None, "health": None, "radio": None,
                 "stop": None, "volume": None, "call": None}
# Weather asked to the server for a spoken answer: waited this long at most
WEATHER_ANSWER_TIMEOUT = 10
# TV contacts (names that can be called by voice) asked again this often
CONTACTS_REFRESH_SECONDS = 600
# A click while it rings waits this long (seconds): a click on "Decline" of
# the TV page declines instead of answering
CLICK_DECLINE_GRACE = 0.5
# Settings applied: the agent restarts this long after telling the TV page
# (systemd starts it again 10 s later, Restart=always)
SETTINGS_RESTART_DELAY = 1.5
# Call asked by voice refused by the server: sentence said by the robot
CALL_ERROR_SENTENCES = {"DEVICE_OFFLINE": "voice.callOffline", "DEVICE_BUSY": "voice.callBusy"}

# Version name accepted in an update request (signed tag of the public repository)
VERSION_PATTERN = re.compile(r"^v\d{1,4}\.\d{1,4}\.\d{1,4}$")


def installed_version():
    """Version written by install.sh (VERSION file), or "unknown"."""
    try:
        text = (config.BASE_DIR / "VERSION").read_text(encoding="utf-8").strip()
    except (OSError, AttributeError):
        return "unknown"
    return re.sub(r"[^A-Za-z0-9._+-]", "", text)[:40] or "unknown"


def weather_place():
    """Town, postal code and country of config.py, or None if none is set."""
    place = {key: str(getattr(config, name, None) or "").strip()[:80]
             for key, name in (("city", "WEATHER_CITY"), ("postcode", "WEATHER_POSTCODE"),
                               ("country", "WEATHER_COUNTRY"))}
    return place if place["city"] or place["postcode"] else None


class TVControlAgent:
    def __init__(self):
        self.ws = None
        self.loop = None

        self.reconnect_delay = 2
        self.max_reconnect_delay = 30
        self.heartbeat_interval = 25

        # Refusal by the server (device not authorized or secret refused):
        # retry at a fixed interval (config.UNAUTHORIZED_RETRY_DELAY)
        self.rejected_by_server = False
        self.rejection_notice_shown = False
        # True once the server confirmed the registration (register_ack)
        self.registered = False

        # Current call state
        self.call_window = False
        self.current_call_id = None
        # Call accepted and in progress (after the click), or None: the
        # self-repair never acts during a call (agent_state.json, inCall)
        self.active_call_id = None
        # Call made FROM this TV ("call from my own TV"), or None
        self.outgoing_call_id = None
        self.alert_sound = AlertSound()
        self.call_timeout_task = None

        # TV page connected to the server (told by the server in its answer
        # to the heartbeat), or None if unknown (server of an older version)
        self.display_connected = None
        # Time when the server said the TV page was stuck during a call
        # (display_stuck): selfheal.py restarts Chromium after it
        self.display_stuck_at = None
        self.alive_interval = 30
        # Spoken commands (model loaded outside calls only) and last one done
        self.voice = voice_commands.VoiceCommands()
        # While it rings, the recognizer reads its partial results ("Robot, décroche")
        self.voice.is_ringing = lambda: bool(self.call_window and self.current_call_id)
        self.last_voice_command_at = 0.0
        # Weather asked to the server for a spoken answer (future), or None
        self.weather_waiter = None
        # Radio asked by voice, and the TV contacts that can be called by voice
        self.radio = radio.Radio()
        self.contacts = []
        self.contacts_asked_at = 0.0
        # Name of the contact called by voice, until the call starts or is refused
        self.voice_call_name = None
        self.voice.set_choices(stations=radio.stations())

    # ---------------------------------------------------------
    # SIGUSR1 signal
    # ---------------------------------------------------------

    def install_signal_handler(self):
        """Installs the SIGUSR1 handler. Must be called from the main thread."""
        signal.signal(signal.SIGUSR1, self.handle_sigusr1)
        print("✅ SIGUSR1 handler installed")

    def handle_sigusr1(self, signum, frame):
        """
        The signal handler stays light:
        it schedules the acceptance in the asyncio loop.
        """
        if self.loop is None or self.loop.is_closed():
            print("⚠️ SIGUSR1 received, but the asyncio loop is not available")
            return

        try:
            self.loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.on_mouse_click_async())
            )
        except RuntimeError as e:
            print(f"⚠️ Cannot handle SIGUSR1: {e}")

    # ---------------------------------------------------------
    # WebSocket connection and reconnection
    # ---------------------------------------------------------

    async def connect(self):
        """
        Connection loop: connects to the server, starts the agent tasks,
        then reconnects as soon as the connection is lost or refused.
        """
        while True:
            try:
                print(f"📡 Connecting to {config.SERVER_URL}...")
                self.ws = await websockets.connect(config.SERVER_URL)
                print("✅ WebSocket connected")

                self.reconnect_delay = 2
                self.rejected_by_server = False
                self.registered = False
                await self.register_device()
                await self.run_session()

            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"❌ Connection error: {e}")

            await self.wait_before_reconnect()

    async def run_session(self):
        """
        Runs the message listener and the heartbeat while the connection
        is open. When the server closes the connection, the listener ends:
        the heartbeat is then stopped so the agent can reconnect.
        """
        heartbeat = asyncio.create_task(self.heartbeat_task())
        try:
            await self.listen_messages()
        finally:
            self.registered = False
            self.display_connected = None
            # Connection lost: the "hangup" of the accepted call may never
            # come (the server ends the calls of a disconnected agent)
            self.active_call_id = None
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
            try:
                await self.ws.close()
            except Exception:
                pass

    async def wait_before_reconnect(self):
        """
        Waits before the next attempt:
        - fixed delay if the server refused the device (waiting for authorization);
        - otherwise growing delay (2 s, 3 s, 4.5 s... up to 30 s).
        """
        if self.rejected_by_server:
            delay = config.UNAUTHORIZED_RETRY_DELAY
            print(t("agent.retryUnauthorized", delay=delay))
        else:
            delay = self.reconnect_delay
            print(f"⏳ Reconnecting in {delay}s...")
            self.reconnect_delay = min(
                self.reconnect_delay * 1.5,
                self.max_reconnect_delay,
            )
        await asyncio.sleep(delay)

    def show_rejection_notice(self, data):
        """
        Shows why the server refuses the device and how to get the
        authorization. The full message is only shown once; the next
        attempts show a short reminder.
        """
        self.rejected_by_server = True
        error_code = data.get("errorCode")

        if self.rejection_notice_shown:
            print(t("agent.stillRefused", code=error_code))
            return
        self.rejection_notice_shown = True

        if error_code == "DEVICE_NOT_AUTHORIZED":
            print(t(
                "agent.notAuthorized",
                device_id=config.RASPBERRY_ID,
                code=device_code(config.DEVICE_SECRET),
                server=config.SERVER_URL,
                contact=data.get("adminContact") or t("agent.adminFallback"),
                delay=config.UNAUTHORIZED_RETRY_DELAY,
            ))
        else:
            print(t(
                "agent.secretRefused",
                device_id=config.RASPBERRY_ID,
                message=data.get("message", ""),
            ))

    async def register_device(self):
        """Sends the registration message of the Raspberry Pi."""
        msg = {
            "type": "register_device",
            "deviceId": config.RASPBERRY_ID,
            "secretKey": config.DEVICE_SECRET,
            "name": f"Raspberry {config.RASPBERRY_ID}",
            "location": "Living Room",
            # The server answers in this language
            "lang": config.LANGUAGE,
            # Call believed in progress: after a server restart, the server
            # answers "hangup" (the TV is given back, the ringtone stops)
            "activeCallId": self.outgoing_call_id or self.current_call_id,
            # Installed version (shown by node admin.js list)
            "version": installed_version(),
            # Place of the weather of the home screen (config.py), or None
            "weatherPlace": weather_place(),
        }
        await self.send_message(msg)
        print(f"✅ Registration sent: {config.RASPBERRY_ID}")

    async def send_message(self, data):
        """Sends a JSON message through the WebSocket if it is connected."""
        if not self.ws:
            print("⚠️ WebSocket not connected")
            return

        try:
            await self.ws.send(json.dumps(data))
        except Exception as e:
            print(f"❌ Send error: {e}")

    # ---------------------------------------------------------
    # Server messages
    # ---------------------------------------------------------

    async def listen_messages(self):
        """Listens to the incoming messages of the server."""
        try:
            async for message in self.ws:
                data = json.loads(message)
                print("📨 Message received:", data)
                await self.handle_message(data)

        except asyncio.CancelledError:
            print("🛑 Message listener stopped")
            raise
        except Exception as e:
            print(f"❌ Listener error: {e}")

    async def handle_message(self, data):
        """Routes the messages according to their type."""
        msg_type = data.get("type")

        if msg_type == "register_ack":
            self.registered = True
            print(f"✅ Status: {data.get('status', 'registered')}")
            if self.rejection_notice_shown:
                print(t("agent.nowAuthorized"))
                self.rejection_notice_shown = False
            await self.ask_contacts()
            await self.send_radio_state()
            # Notes of the calendar: the home screen shows those of the day
            await self.send_calendar()

        elif msg_type in ("offer", "incoming_call"):
            await self.handle_incoming_call(data)

        elif msg_type == "hangup":
            await self.handle_hangup(data)

        elif msg_type == "outgoing_call_start":
            await self.handle_outgoing_call_start(data)

        elif msg_type == "accept_call":
            # Echo of our own message: ignore it.
            print("ℹ️ accept_call echo received (ignored)")

        elif msg_type == "call_accepted_sync":
            await self.handle_call_accepted_sync(data)

        elif msg_type == "display_stuck":
            self.handle_display_stuck(data)

        elif msg_type == "diagnose_request":
            # In a task: the checks take a few seconds, the calls must not wait
            asyncio.create_task(self.handle_diagnose_request(data))

        elif msg_type == "update_request":
            await self.handle_update_request(data)

        elif msg_type == "error":
            error_code = data.get("errorCode")
            # UNAUTHORIZED before register_ack = secret refused at registration
            # (afterwards, it only concerns a refused action)
            if error_code == "DEVICE_NOT_AUTHORIZED" or (
                error_code == "UNAUTHORIZED" and not self.registered
            ):
                self.show_rejection_notice(data)
            else:
                print(f"❌ Server error: {data.get('message', 'Unknown error')}")

        elif msg_type == "weather":
            if self.weather_waiter is not None and not self.weather_waiter.done():
                self.weather_waiter.set_result(data)

        elif msg_type == "tv_contacts":
            self.set_contacts(data.get("contacts"))

        elif msg_type == "radio_stop":
            # "Stop" button of the TV page
            await self.stop_radio()

        elif msg_type == "settings_request":
            await self.send_settings()

        elif msg_type == "settings_apply":
            asyncio.create_task(self.apply_settings(data.get("values")))

        elif msg_type == "calendar_request":
            await self.send_calendar()

        elif msg_type == "calendar_save":
            notes, error = calendar_store.save_note(config.BASE_DIR, data.get("note"))
            await self.send_calendar(notes, done="save", error=error)

        elif msg_type == "calendar_delete":
            notes, error = calendar_store.delete_note(config.BASE_DIR, data.get("id"))
            await self.send_calendar(notes, done="delete", error=error)

        elif msg_type == "tv_call_error":
            # Call asked by voice refused (contact offline, busy...): the robot says why
            name, self.voice_call_name = self.voice_call_name, None
            if name and not self.in_call():
                key = CALL_ERROR_SENTENCES.get(data.get("errorCode"), "voice.callFailed")
                self.voice_answer_task = asyncio.create_task(self.say_text(t(key, name=name)))

        elif msg_type in ("pong", "heartbeat_ack"):
            if "displayConnected" in data:
                self.display_connected = bool(data["displayConnected"])

    # ---------------------------------------------------------
    # Health report
    # ---------------------------------------------------------

    async def handle_diagnose_request(self, data):
        """Runs the checks (in a thread) and sends the report to the server."""
        request_id = data.get("requestId")
        print(f"🩺 Health report requested ({request_id})")
        # During a call, the TV is not asked its state (it must not be disturbed)
        in_call = bool(self.call_window or self.current_call_id or self.outgoing_call_id)
        try:
            report = await asyncio.to_thread(diagnostics.run_checks, in_call)
        except Exception as e:
            print(f"❌ Health report failed: {e}")
            report = {"version": diagnostics.REPORT_VERSION, "error": str(e)[:200]}
        await self.send_message({
            "type": "diagnose_report",
            "requestId": request_id,
            "report": report,
        })
        print(f"🩺 Health report sent ({request_id})")

    # ---------------------------------------------------------
    # Remote update
    # ---------------------------------------------------------

    async def handle_update_request(self, data):
        """
        The server tells that a version exists (node admin.js update): only
        its name is written to update_request. The update itself is made by
        update.sh (as root, started by appelermamie-update.path), which only
        installs a version signed by the key of the Raspberry, after the call.
        """
        request_id = data.get("requestId")
        version = data.get("version")
        if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
            print(f"⚠️ Update request refused: invalid version {version!r}")
            status = "invalid"
        else:
            path = config.BASE_DIR / "update_request"
            tmp = path.with_name(path.name + ".tmp")
            try:
                tmp.write_text(version + "\n", encoding="utf-8")
                os.replace(tmp, path)
                print(f"🔄 Update to {version} requested (installed: {installed_version()})")
                status = "accepted"
            except OSError as e:
                print(f"❌ Update request not written: {e}")
                status = "error"
        await self.send_message({
            "type": "update_ack",
            "requestId": request_id,
            "status": status,
            "version": version if status != "invalid" else None,
            "installed": installed_version(),
        })

    # ---------------------------------------------------------
    # Incoming call and ringtone
    # ---------------------------------------------------------

    async def handle_incoming_call(self, data):
        """Stores the call and starts the ringtone without blocking asyncio."""
        caller_name = data.get("callerName") or t("tts.someone")
        call_id = data.get("callId")

        if not call_id:
            print("⚠️ Call received without callId, ignored")
            return

        self.current_call_id = call_id
        self.call_window = True
        await self.stop_radio()

        print(f"\n{'=' * 50}")
        print(f"📞 INCOMING CALL from '{caller_name}' (callId={call_id})")
        print(f"{'=' * 50}")

        def start_sound():
            self.alert_sound.play(caller_name)

            # The call may have been cancelled or accepted while ringing.
            if not self.call_window or self.current_call_id != call_id:
                self.alert_sound.stop()
                return

            if self.loop and not self.loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    self.send_sound_started(call_id),
                    self.loop,
                )
                self.call_timeout_task = asyncio.run_coroutine_threadsafe(
                    self.close_call_window_after_delay(
                        config.CALL_DURATION,
                        call_id,
                    ),
                    self.loop,
                )

        threading.Thread(target=start_sound, daemon=True).start()

    async def send_sound_started(self, call_id):
        """Tells the server that the ringtone has started."""
        await self.send_message({
            "type": "sound_started",
            "callId": call_id,
        })
        print("✅ 'sound_started' signal sent")

    async def close_call_window_after_delay(self, seconds, call_id):
        """Closes the unanswered call after the configured delay."""
        await asyncio.sleep(seconds)

        if self.call_window and self.current_call_id == call_id:
            print(f"⏰ Call expired after {seconds}s without an answer")
            self.alert_sound.stop()
            self.call_window = False
            self.current_call_id = None
            self.call_timeout_task = None

            await self.send_message({
                "type": "hangup",
                "callId": call_id,
                "reason": "no_answer",
            })

    async def handle_outgoing_call_start(self, data):
        """
        Call made FROM this TV (asked by the owner phone): the TV is turned on,
        on the input of the Raspberry, without ringtone. The TV page makes the
        call. The mouse does not hang up (the phone does).
        """
        call_id = data.get("callId")
        if not call_id:
            return
        self.outgoing_call_id = call_id
        self.voice_call_name = None
        await self.stop_radio()
        print(f"📺 Call from this TV (callId={call_id}): turning the TV on")
        # The CEC commands take several seconds: run outside the asyncio loop
        await asyncio.to_thread(tv_on_and_accept)

    async def handle_hangup(self, data):
        """Handles a hangup received from the server."""
        hangup_call_id = data.get("callId")
        print(f"☎️ Hangup received for callId={hangup_call_id}")

        # End of a call made from this TV: the TV is given back
        if hangup_call_id and hangup_call_id == self.outgoing_call_id:
            self.outgoing_call_id = None
            await asyncio.to_thread(tv_return)
            await self.ask_contacts()
            return

        # End of the accepted call: the conversation is over
        if hangup_call_id and hangup_call_id == self.active_call_id:
            self.active_call_id = None
            print("✅ Call ended")
            # The caller may be a new TV contact
            await self.ask_contacts()
            return

        if hangup_call_id != self.current_call_id:
            print("ℹ️ Hangup ignored: not about the current call")
            return

        self.cancel_call_timeout()
        self.call_window = False
        self.current_call_id = None

        tv_return()
        self.alert_sound.stop()

    async def handle_call_accepted_sync(self, data):
        """Synchronizes the agent when the call is accepted from the HTML page."""
        call_id = data.get("callId")
        print(f"🔄 Call {call_id} accepted from another client")

        if call_id != self.current_call_id:
            print("⚠️ Sync ignored: different callId")
            return

        if not self.call_window:
            print("ℹ️ Call window already closed")
            return

        self.cancel_call_timeout()
        self.alert_sound.stop()

        self.call_window = False
        self.current_call_id = None
        self.active_call_id = call_id

        print("✅ Sync done")
        # The CEC commands take several seconds: run them outside the
        # asyncio loop so that the WebSocket keeps answering meanwhile.
        await asyncio.to_thread(tv_on_and_accept)

    def handle_display_stuck(self, data):
        """
        The TV page did not start the video of the accepted call (camera
        blocked, page frozen): the server ended the call. selfheal.py restarts
        Chromium (agent_state.json, displayStuckAt) once no call is in progress.
        """
        print(f"⚠️ TV page stuck during the call {data.get('callId')} ({data.get('reason')}): "
              "the screen will be restarted")
        if data.get("callId") == self.active_call_id:
            self.active_call_id = None
        self.display_stuck_at = time.time()
        self.write_agent_state()

    # ---------------------------------------------------------
    # Accepting: mouse or SIGUSR1
    # ---------------------------------------------------------

    def cancel_call_timeout(self):
        """Cancels the call expiration timer, if active."""
        if self.call_timeout_task:
            self.call_timeout_task.cancel()
            self.call_timeout_task = None

    def on_mouse_click(self):
        """
        Synchronous entry point for a click detected by evdev.
        Schedules the handling in the asyncio loop.
        """
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.on_mouse_click_after_page())
            )

    async def on_mouse_click_after_page(self):
        """
        A click while it rings answers, unless it was on "Decline" of the TV
        page (a real mouse): the page declines and the server tells the agent
        within a moment, so the click waits that long first.
        """
        call_id = self.current_call_id
        if self.call_window and call_id and self.display_connected:
            await asyncio.sleep(CLICK_DECLINE_GRACE)
            if not self.call_window or self.current_call_id != call_id:
                print("ℹ️ Click while it rang: the call was declined (or answered) on the TV page")
                return
        await self.on_mouse_click_async()

    async def on_mouse_click_async(self):
        """Accepts the active call, whether triggered by the mouse or SIGUSR1."""
        if not self.call_window or not self.current_call_id:
            if self.radio.on and not self.in_call():
                # The button stops the radio
                await self.stop_radio()
                return
            print("ℹ️ No active call to accept")
            return

        call_id = self.current_call_id

        # Close the call state before the external operations so that a
        # second click or signal cannot trigger a second acceptance.
        self.call_window = False
        self.current_call_id = None
        self.active_call_id = call_id
        self.cancel_call_timeout()

        self.alert_sound.stop()

        # Accept first: the TV screen opens the camera and starts the video
        # while the TV is turning on (the CEC commands take several seconds).
        await self.send_message({
            "type": "accept_call",
            "callId": call_id,
        })

        print(f"✅ Call {call_id} accepted")
        await asyncio.to_thread(tv_on_and_accept)

    @staticmethod
    def find_mouse():
        """
        Returns the mouse used as the answer button, or None if none is found.

        - config.MOUSE_DEVICE set: only that device is used.
        - config.MOUSE_DEVICE = None (automatic): the first device with a left
          button is used, whatever its model or USB port. Real mice (relative
          movement) are preferred over other devices with a left button
          (touchpads, etc.).
        """
        if config.MOUSE_DEVICE:
            try:
                return InputDevice(config.MOUSE_DEVICE)
            except OSError:
                return None

        mice, other_pointers = [], []
        for path in sorted(list_devices()):
            try:
                device = InputDevice(path)
                capabilities = device.capabilities()
            except OSError:
                continue  # unplugged meanwhile, or not readable
            if ecodes.BTN_LEFT not in capabilities.get(ecodes.EV_KEY, []):
                device.close()
            elif ecodes.REL_X in capabilities.get(ecodes.EV_REL, []):
                mice.append(device)
            else:
                other_pointers.append(device)

        candidates = mice + other_pointers
        for unused in candidates[1:]:
            unused.close()
        return candidates[0] if candidates else None

    # ---------------------------------------------------------
    # Remote control of the TV (HDMI-CEC)
    # ---------------------------------------------------------

    async def on_remote_key(self, key):
        """
        Key of the remote control of the TV ("up", "down", "left", "right",
        "ok", "back"). While it rings: Back declines; the arrows and OK go to
        the TV page (Answer / Decline chosen with the arrows, OK on the chosen
        one), or OK answers (like the mouse) if the page is not connected.
        During a received call: Back hangs up. Otherwise the key goes to the
        TV page (its menu), through the server.
        """
        if self.call_window and self.current_call_id:
            if key == "back":
                await self.decline_call()
            elif self.display_connected:
                await self.send_message({"type": "remote_key", "key": key})
            elif key == "ok":
                print("📺 OK on the remote control while it rings: answering")
                await self.on_mouse_click_async()
            return
        if self.active_call_id and key == "back":
            call_id = self.active_call_id
            print(f"📺 Back on the remote control during the call {call_id}: hanging up")
            self.active_call_id = None
            await self.send_message({"type": "hangup", "callId": call_id})
            return
        await self.send_message({"type": "remote_key", "key": key})

    # ---------------------------------------------------------
    # Sound near the TV (microphone, volume only)
    # ---------------------------------------------------------

    def in_call(self):
        """It rings, a call is in progress, or a call is made from this TV."""
        return bool(self.call_window or self.current_call_id or self.active_call_id
                    or self.outgoing_call_id)

    def in_conversation(self):
        """A call answered or made from this TV is in progress (not only ringing)."""
        return bool(self.active_call_id or self.outgoing_call_id)

    def should_listen_sound(self):
        """
        The microphone is listened to outside calls, connected to the server,
        and while it rings ("Robot, décroche"); not during the conversation.
        """
        return self.registered and not self.in_conversation()

    async def on_sound_activity(self, active):
        """
        A sound starts / ended near the TV: the robot of the TV page reacts
        (not to the radio: it listens to it, with its headphones).
        """
        if self.registered and not (active and self.radio.on):
            await self.send_message({"type": "sound_activity", "active": active})

    async def on_voice_command(self, command):
        """
        Spoken command recognized: "hello" ("Robot bonjour"), "time" ("Robot,
        quelle heure est-il ?"), "weather" ("Robot, quel temps fait-il ?").
        Once every few seconds at most; nothing during a call. The answer runs
        apart: the microphone keeps being read (and ignored) while the robot
        speaks, so that it never hears its own voice afterwards.
        """
        ringing = bool(self.call_window and self.current_call_id)
        if command in (voice_commands.LISTENING, voice_commands.LISTENING_OFF):
            # "Robot" heard: eyes and mouth of the robot green while it listens;
            # the radio (or the ringtone) is turned down meanwhile, to hear the question
            listening = command == voice_commands.LISTENING
            if ringing:
                await self.send_message({"type": "voice_command", "command": command})
                card = tts_audio.find_ringing_card()
                # Ringtone silent while the robot listens (it covers the voice), back after
                await asyncio.to_thread(tts_audio.set_card_volume, card, 0 if listening else 100)
            elif not self.in_call():
                await self.send_message({"type": "voice_command", "command": command})
                await asyncio.to_thread(self.radio.duck if listening else self.radio.unduck)
            return
        if command in RINGING_COMMANDS:
            # "Robot, décroche" / "Robot, raccroche": only while it rings
            if ringing:
                print(f"🗣️ \"{command}\" said while it rings")
                await asyncio.to_thread(tts_audio.set_max_volume, tts_audio.find_ringing_card())
                if command == "answer":
                    await self.on_mouse_click_async()
                else:
                    await self.decline_call()
            return
        now = time.monotonic()
        name = command.partition(":")[0]
        if name not in VOICE_ANSWERS or self.in_call() or now - self.last_voice_command_at < VOICE_COMMAND_INTERVAL:
            return
        self.last_voice_command_at = now
        # The robot must not hear itself (until its answer is over)
        self.voice.mute(60)
        self.voice_answer_task = asyncio.create_task(self.answer_voice_command(command))

    async def answer_voice_command(self, command):
        """Prepares the answer, makes the robot of the TV page move as long as it speaks, says it."""
        name, _, value = command.partition(":")
        print(f"🗣️ Spoken command \"{command}\": the robot answers")
        # The speaker plays one sound at a time: the radio waits while the robot speaks
        radio_was_on = self.radio.on
        await asyncio.to_thread(self.radio.pause)
        after = None
        try:
            if name == "stop":
                # Nothing to say: the radio stops
                await self.stop_radio()
                return
            if VOICE_ANSWERS[name]:
                text = None
                wav = await asyncio.to_thread(tts_audio.spoken_wav, VOICE_ANSWERS[name])
            elif name == "time":
                text = robot_answers.time_sentence(datetime.datetime.now())
            elif name == "weather":
                text = robot_answers.weather_sentence(await self.ask_weather())
            elif name == "health":
                # The health report (about 2 s; the TV is asked through CEC, no call now)
                report = await asyncio.to_thread(diagnostics.run_checks)
                text = robot_answers.health_sentence(report, self.registered)
            elif name == "radio":
                station = radio.find(value) if value else radio.default_station()
                text = t("voice.radioOn", station=station["name"]) if station else t("voice.radioNone")
                if station:
                    turned_on = not radio_was_on
                    after = lambda: self.start_radio(station, turned_on=turned_on)  # noqa: E731
            elif name == "volume":
                level = int(value) if value.isdigit() else 0
                if not tts_audio.save_volume_level(level):
                    return
                text = t("voice.volume", level=level)
            else:  # call
                contact = next((c for c in self.contacts if c["deviceId"] == value), None)
                if contact is None:
                    return
                text = t("voice.calling", name=contact["name"])
                radio_was_on = False
                await self.stop_radio()
                self.voice_call_name = contact["name"]
                after = lambda: self.send_message({"type": "tv_call_request", "targetDeviceId": contact["deviceId"]})  # noqa: E731
            if text is not None:
                wav = await asyncio.to_thread(tts_audio.text_wav, text)
            seconds = await asyncio.to_thread(tts_audio.wav_seconds, wav) if wav else 0
            message = {"type": "voice_command", "command": name}
            if seconds:
                message["seconds"] = round(min(max(seconds, 1), 30), 1)
            await self.send_message(message)
            await asyncio.to_thread(tts_audio.play_wav, wav)
            if after is not None:
                radio_was_on = False
                await after()
        except Exception as e:
            print(f"⚠️ Spoken answer failed: {e}")
        finally:
            if radio_was_on and self.radio.on and not self.in_call():
                await asyncio.to_thread(self.radio.resume)
            self.voice.mute(0.8)

    async def say_text(self, text):
        """Says a sentence (the robot of the TV page looks clever meanwhile)."""
        self.voice.mute(60)
        radio_was_on = self.radio.on
        await asyncio.to_thread(self.radio.pause)
        try:
            wav = await asyncio.to_thread(tts_audio.text_wav, text)
            seconds = await asyncio.to_thread(tts_audio.wav_seconds, wav) if wav else 0
            message = {"type": "voice_command", "command": "time"}
            if seconds:
                message["seconds"] = round(min(max(seconds, 1), 30), 1)
            await self.send_message(message)
            await asyncio.to_thread(tts_audio.play_wav, wav)
        except Exception as e:
            print(f"⚠️ Sentence not said: {e}")
        finally:
            if radio_was_on and self.radio.on and not self.in_call():
                await asyncio.to_thread(self.radio.resume)
            self.voice.mute(0.8)

    async def start_radio(self, station, turned_on=True):
        """
        Plays a station asked by voice; the TV page shows it (robot with
        headphones). Radio turned on (not another station): at volume 2.
        """
        if turned_on:
            tts_audio.save_volume_level(radio.START_LEVEL)
        await asyncio.to_thread(self.radio.play, station)
        await self.send_message({"type": "sound_activity", "active": False})
        await self.send_radio_state()

    async def stop_radio(self):
        """Stops the radio (stop, the button, a call)."""
        if self.radio.on:
            await asyncio.to_thread(self.radio.stop)
            await self.send_radio_state()

    async def send_radio_state(self):
        """Radio playing or not, and its station, for the TV page."""
        if not self.registered:
            return
        state = {"type": "radio_state", "playing": self.radio.on}
        if self.radio.on:
            state["station"] = self.radio.station["name"]
            state["frequency"] = self.radio.station["frequency"]
        await self.send_message(state)

    # ---------------------------------------------------------
    # Settings page of the TV (settings_store.py)
    # ---------------------------------------------------------

    def current_settings(self):
        """Settings shown on the TV page, and the radio stations (not changed there)."""
        return {
            "language": config.LANGUAGE,
            "ringtoneLevel": settings_store.ringtone_level(config.RINGTONE_VOLUME),
            "ringtoneVoiceLevel": settings_store.voice_level(config.VOICE_VOLUME),
            "city": config.WEATHER_CITY or "",
            "postcode": config.WEATHER_POSTCODE or "",
            "country": config.WEATHER_COUNTRY or "",
        }

    async def send_settings(self):
        await self.send_message({
            "type": "settings",
            "values": self.current_settings(),
            "stations": [{"name": s["name"], "frequency": s["frequency"]} for s in radio.stations()],
        })

    async def apply_settings(self, values):
        """
        "Apply" confirmed on the TV: valid settings saved in settings.json; a
        new language gets its speech model; the agent restarts if the
        language or the place changed (the TV page reloads itself).
        """
        if self.in_call():
            await self.send_message({"type": "settings_applied", "ok": False, "reason": "call"})
            return
        changes = {key: value for key, value in settings_store.validate(values).items()
                   if getattr(config, key, None) != value}
        if not changes:
            await self.send_message({"type": "settings_applied", "ok": True, "restart": False})
            return
        if not settings_store.save(config.BASE_DIR, changes):
            await self.send_message({"type": "settings_applied", "ok": False, "reason": "save"})
            return
        print(f"⚙️ Settings changed on the TV: {', '.join(sorted(changes))}")
        voice_ready = True
        if "LANGUAGE" in changes:
            await self.send_message({"type": "settings_progress", "step": "voiceModel"})
            voice_ready = await asyncio.to_thread(voice_model.download, changes["LANGUAGE"])
        restart = any(key not in ("RINGTONE_VOLUME", "VOICE_VOLUME") for key in changes)
        for key, value in changes.items():
            setattr(config, key, value)
        await self.send_message({"type": "settings_applied", "ok": True, "restart": restart,
                                 "language": config.LANGUAGE, "voiceModel": voice_ready})
        if restart:
            await asyncio.sleep(SETTINGS_RESTART_DELAY)
            self.restart_agent()

    async def send_calendar(self, notes=None, done=None, error=None):
        """Notes of the calendar to the TV page (after a change: done, error)."""
        message = {"type": "calendar",
                   "notes": calendar_store.load(config.BASE_DIR) if notes is None else notes}
        if done:
            message["done"] = done
            message["ok"] = error is None
            if error:
                message["error"] = error
                print(f"⚠️ Calendar: note not {'saved' if done == 'save' else 'deleted'} ({error})")
            else:
                print(f"📅 Calendar: note {'saved' if done == 'save' else 'deleted'}")
        await self.send_message(message)

    def restart_agent(self):
        """Ends the agent: systemd starts it again with the new settings."""
        print("⚙️ Restarting the agent with the new settings")
        self.radio.stop()
        self.alert_sound.stop()
        os._exit(0)

    async def ask_contacts(self):
        """Asks the server for the TV contacts (names that can be called by voice)."""
        if self.registered:
            self.contacts_asked_at = time.monotonic()
            await self.send_message({"type": "tv_contacts_request"})

    def set_contacts(self, contacts):
        """TV contacts given by the server: their names are added to the spoken commands."""
        if not isinstance(contacts, list):
            return
        self.contacts = [
            {"deviceId": c["deviceId"], "name": c["name"].strip()[:40]}
            for c in contacts
            if isinstance(c, dict) and isinstance(c.get("deviceId"), str) and isinstance(c.get("name"), str)
            and c["name"].strip()
        ][:50]
        self.voice.set_choices(contacts=self.contacts)

    async def ask_weather(self):
        """Weather of the place of this Raspberry, asked to the server (None if no answer)."""
        self.weather_waiter = asyncio.get_running_loop().create_future()
        await self.send_message({"type": "weather_request"})
        try:
            return await asyncio.wait_for(self.weather_waiter, WEATHER_ANSWER_TIMEOUT)
        except asyncio.TimeoutError:
            return None
        finally:
            self.weather_waiter = None

    async def decline_call(self):
        """Back on the remote control while it rings: the call is declined."""
        call_id = self.current_call_id
        print(f"📺 Back on the remote control while it rings: call {call_id} declined")
        self.cancel_call_timeout()
        self.call_window = False
        self.current_call_id = None
        self.alert_sound.stop()
        await self.send_message({"type": "hangup", "callId": call_id})
        await asyncio.to_thread(tv_return)

    @staticmethod
    def keep_cec_ready():
        """The Raspberry stays declared to the TV, so the TV keeps sending the keys."""
        ensure = getattr(tv_control, "ensure_cec_ready", None)
        if ensure is None:
            return
        try:
            ensure()
        except Exception as e:
            print(f"⚠️ CEC not ready: {e}")

    @staticmethod
    def keep_screen_mode():
        """A 4K TV stays in 1920 x 1080 (display_mode.py), even plugged back in."""
        try:
            display_mode.ensure_screen_mode()
        except Exception as e:
            print(f"⚠️ Screen mode not checked: {e}")

    async def mouse_listener(self):
        """
        Listens to mouse clicks and accepts the call during a call window.
        Runs for the whole life of the agent: if the mouse is missing or
        unplugged, it is searched again every config.MOUSE_RETRY_DELAY seconds
        and used again as soon as it is plugged back in (any USB port).
        """
        missing_notice_shown = False
        while True:
            device = self.find_mouse()
            if device is None:
                if not missing_notice_shown:
                    print(f"⚠️ No mouse found, searching again every {config.MOUSE_RETRY_DELAY}s...")
                    missing_notice_shown = True
                await asyncio.sleep(config.MOUSE_RETRY_DELAY)
                continue

            missing_notice_shown = False
            print(f"🖱️ Mouse found: {device.name} ({device.path})")
            try:
                async for event in device.async_read_loop():
                    # EV_KEY includes buttons and sometimes keyboard keys.
                    # Only the left button is kept (BTN_LEFT).
                    if (
                        event.type == ecodes.EV_KEY
                        and event.code == ecodes.BTN_LEFT
                        and event.value == 1
                        and self.call_window
                    ):
                        print("🖱️ Left click detected during the call")
                        await self.on_mouse_click_async()
            except OSError as e:
                # Raised when the mouse is unplugged
                print(f"⚠️ Mouse disconnected ({e}), searching for it again...")
            finally:
                try:
                    device.close()
                except Exception:
                    pass
            await asyncio.sleep(config.MOUSE_RETRY_DELAY)

    # ---------------------------------------------------------
    # Heartbeat
    # ---------------------------------------------------------

    async def heartbeat_task(self):
        """Periodically sends a heartbeat to the server."""
        try:
            while True:
                await asyncio.sleep(self.heartbeat_interval)
                await self.send_message({
                    "type": "heartbeat",
                    "timestamp": time.time(),
                })
                # Radio stream ended by itself; the TV page reloaded meanwhile
                if await asyncio.to_thread(self.radio.check) or self.radio.on:
                    await self.send_radio_state()
                if time.monotonic() - self.contacts_asked_at > CONTACTS_REFRESH_SECONDS:
                    await self.ask_contacts()
        except asyncio.CancelledError:
            print("❌ Heartbeat stopped")
            raise

    # ---------------------------------------------------------
    # Alive signal (systemd) and state for the self-repair
    # ---------------------------------------------------------

    @staticmethod
    def notify_systemd(message):
        """Message to systemd (WatchdogSec of tv-control.service); nothing outside systemd."""
        address = os.environ.get("NOTIFY_SOCKET")
        if not address:
            return
        if address.startswith("@"):
            address = "\0" + address[1:]
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
                sock.connect(address)
                sock.send(message.encode())
        except OSError as e:
            print(f"⚠️ systemd notification failed: {e}")

    def agent_state(self):
        """State read by selfheal.py (never during a call does it repair anything)."""
        return {
            "time": time.time(),
            "registered": self.registered,
            "rejected": self.rejected_by_server,
            "inCall": self.in_call(),
            "displayConnected": self.display_connected,
            "displayStuckAt": self.display_stuck_at,
        }

    def write_agent_state(self):
        path = config.BASE_DIR / "agent_state.json"
        tmp = path.with_name(path.name + ".tmp")
        try:
            tmp.write_text(json.dumps(self.agent_state()), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as e:
            print(f"⚠️ Agent state not written: {e}")

    async def alive_task(self):
        """
        Every 30 s, connected or not: alive signal to systemd (an agent stuck
        for 2 minutes is restarted) and state written for selfheal.py.
        """
        while True:
            self.notify_systemd("WATCHDOG=1")
            self.write_agent_state()
            # Declared again if the configuration was lost (TV unplugged...)
            await asyncio.to_thread(self.keep_cec_ready)
            # 1920 x 1080 again if the TV gave its 4K mode back
            await asyncio.to_thread(self.keep_screen_mode)
            await asyncio.sleep(self.alive_interval)

    # ---------------------------------------------------------
    # Startup and shutdown
    # ---------------------------------------------------------

    async def run(self):
        """Entry point of the agent."""
        self.loop = asyncio.get_running_loop()
        self.install_signal_handler()

        # The mouse is listened to for the whole life of the agent,
        # independently of the connection to the server.
        self.mouse_task = asyncio.create_task(self.mouse_listener())
        self.alive = asyncio.create_task(self.alive_task())
        # Remote control of the TV: same, for the whole life of the agent
        self.remote_task = asyncio.create_task(remote_keys.listen(self.on_remote_key))
        # Volume of the microphone outside calls: the robot of the TV page reacts
        self.sound_task = asyncio.create_task(
            sound_level.listen(self.on_sound_activity, self.should_listen_sound,
                               voice=self.voice, on_command=self.on_voice_command))

        try:
            await self.connect()
        except KeyboardInterrupt:
            print("\n🛑 Stop requested")
        finally:
            self.cancel_call_timeout()
            self.alert_sound.stop()
            self.radio.stop()

            if self.ws:
                await self.ws.close()


if __name__ == "__main__":
    agent = TVControlAgent()

    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        print("\n🛑 Stop requested")
