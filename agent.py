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
- sends a periodic heartbeat;
- sends its health report when the server asks for it (diagnostics.py);
- tells systemd it is alive and writes its state for the self-repair
  (selfheal.py) every 30 s.
"""

import asyncio
import json
import os
import re
import signal
import socket
import threading
import time

import websockets
from evdev import InputDevice, ecodes, list_devices

import config
import diagnostics
import display_mode
import remote_keys
import tv_control
from device_code import device_code
from i18n import t
from tts_audio import AlertSound
from tv_control import tv_on_and_accept, tv_return

# Version name accepted in an update request (signed tag of the public repository)
VERSION_PATTERN = re.compile(r"^v\d{1,4}\.\d{1,4}\.\d{1,4}$")


def installed_version():
    """Version written by install.sh (VERSION file), or "unknown"."""
    try:
        text = (config.BASE_DIR / "VERSION").read_text(encoding="utf-8").strip()
    except (OSError, AttributeError):
        return "unknown"
    return re.sub(r"[^A-Za-z0-9._+-]", "", text)[:40] or "unknown"


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
            return

        # End of the accepted call: the conversation is over
        if hangup_call_id and hangup_call_id == self.active_call_id:
            self.active_call_id = None
            print("✅ Call ended")
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
                lambda: asyncio.create_task(self.on_mouse_click_async())
            )

    async def on_mouse_click_async(self):
        """Accepts the active call, whether triggered by the mouse or SIGUSR1."""
        if not self.call_window or not self.current_call_id:
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
        "ok", "back"). While it rings: OK answers (like the mouse), Back
        declines. During a received call: Back hangs up. Otherwise the key goes
        to the TV page (its menu), through the server.
        """
        if self.call_window and self.current_call_id:
            if key == "ok":
                print("📺 OK on the remote control while it rings: answering")
                await self.on_mouse_click_async()
            elif key == "back":
                await self.decline_call()
            return
        if self.active_call_id and key == "back":
            call_id = self.active_call_id
            print(f"📺 Back on the remote control during the call {call_id}: hanging up")
            self.active_call_id = None
            await self.send_message({"type": "hangup", "callId": call_id})
            return
        await self.send_message({"type": "remote_key", "key": key})

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
            "inCall": bool(self.call_window or self.current_call_id or self.active_call_id
                           or self.outgoing_call_id),
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

        try:
            await self.connect()
        except KeyboardInterrupt:
            print("\n🛑 Stop requested")
        finally:
            self.cancel_call_timeout()
            self.alert_sound.stop()

            if self.ws:
                await self.ws.close()


if __name__ == "__main__":
    agent = TVControlAgent()

    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        print("\n🛑 Stop requested")
