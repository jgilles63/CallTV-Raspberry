#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Main agent:
- handles the WebSocket connection to the signaling server;
- receives the calls;
- detects mouse clicks with evdev;
- accepts a call when SIGUSR1 is received;
- sends a periodic heartbeat;
- sends its health report when the server asks for it (diagnostics.py);
- tells systemd it is alive and writes its state for the self-repair
  (selfheal.py) every 30 s.
"""

import asyncio
import json
import os
import signal
import socket
import threading
import time

import websockets
from evdev import InputDevice, ecodes, list_devices

import config
import diagnostics
from device_code import device_code
from i18n import t
from tts_audio import AlertSound
from tv_control import tv_on_and_accept, tv_return


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
        # Call made FROM this TV ("call from my own TV"), or None
        self.outgoing_call_id = None
        self.alert_sound = AlertSound()
        self.call_timeout_task = None

        # TV page connected to the server (told by the server in its answer
        # to the heartbeat), or None if unknown (server of an older version)
        self.display_connected = None
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

        elif msg_type == "diagnose_request":
            # In a task: the checks take a few seconds, the calls must not wait
            asyncio.create_task(self.handle_diagnose_request(data))

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
        # During a call, cec-client is not run (it must not disturb the TV)
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

        print("✅ Sync done")
        # The CEC commands take several seconds: run them outside the
        # asyncio loop so that the WebSocket keeps answering meanwhile.
        await asyncio.to_thread(tv_on_and_accept)

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
            "inCall": bool(self.call_window or self.current_call_id or self.outgoing_call_id),
            "displayConnected": self.display_connected,
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
