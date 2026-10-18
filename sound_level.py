# ============================================
# FILE: sound_level.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sound heard near the TV (ROADMAP 2.13, level 1): the robot of the home
screen reacts when someone speaks.

The microphone of the camera is read through PipeWire (pw-record: shared
with Chromium, never taken from it) and only its volume is measured, ten
times per second: nothing is recorded, kept or sent, except "a sound starts"
/ "the sound ended" (the agent gives them to the TV page, sound_activity).

The threshold follows the background noise of the room (fan, fridge, quiet
TV): a sound is something clearly louder than it, for a short while.
The agent stops listening during a call and while it rings
(should_listen), and config.VOICE_REACTION = False turns it off.
The same frames go to the spoken commands (voice_commands.py, optional
"voice"): its model is loaded when the listening starts and unloaded when
it stops (a call).
"""

import array
import asyncio
import math
import sys
import time

import config
from call_audio import pipewire_env

RATE = 16000
# Volume measured on 100 ms
FRAME_SAMPLES = RATE // 10
FRAME_BYTES = FRAME_SAMPLES * 2
RECORD_COMMAND = ["pw-record", "--rate", str(RATE), "--channels", "1", "--format", "s16", "-"]

# First second ignored (the microphone starts with a loud click)
STARTUP_FRAMES = 10
# A sound: louder than RATIO x the background noise, and than MIN_LEVEL (of
# 32767; a voice near the screen: 1000 to 6500, quiet room: 100 to 400)
RATIO = 3.0
MIN_LEVEL = 600
# For START_FRAMES x 100 ms in a row; it ends after END_FRAMES x 100 ms of quiet
START_FRAMES = 3
END_FRAMES = 15
# The spoken commands (voice_commands.py) listen sooner than the robot walks:
# a voice far from the microphone, in a big room (TV), is quieter
VOICE_RATIO = 2.0
VOICE_MIN_LEVEL = 250
VOICE_START_FRAMES = 2
# Background noise learnt in the quiet (fast) and in a long sound (slow: a
# sound that never stops, like a TV left loud, stops being "a sound" after
# about ten seconds; speech has pauses, learnt in the quiet)
FLOOR_SPEED_QUIET = 0.05
FLOOR_SPEED_LOUD = 0.002
# "A sound starts" said again during a long sound (the TV page forgets it
# after a while, in case the end is never received)
KEEPALIVE_SECONDS = 5
# Microphone missing or pw-record failed: tried again after this delay
RETRY_DELAY = 30


def level(data):
    """Volume (root mean square, 0 to 32767) of 16-bit mono samples."""
    samples = array.array("h")
    samples.frombytes(data[: len(data) // 2 * 2])
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return 0
    return int(math.sqrt(sum(s * s for s in samples) / len(samples)))


class SoundDetector:
    """Turns volumes (one per 100 ms) into "a sound starts" / "the sound ended"."""

    def __init__(self, ratio=None, min_level=None, start_frames=None):
        # None: the values of the module (read at each use, tests change them)
        self.ratio, self.min_level, self.start_frames = ratio, min_level, start_frames
        self.floor = None
        self.skipped = 0
        self.above = 0
        self.below = 0
        self.active = False

    def threshold(self):
        min_level = self.min_level if self.min_level is not None else MIN_LEVEL
        return max(min_level, (self.floor or 0) * (self.ratio if self.ratio is not None else RATIO))

    def feed(self, volume):
        """True when a sound starts, False when it ended, None otherwise."""
        if self.skipped < STARTUP_FRAMES:
            self.skipped += 1
            return None
        if self.floor is None:
            self.floor = min(volume, self.min_level if self.min_level is not None else MIN_LEVEL)
        if volume > self.threshold():
            self.above += 1
            self.below = 0
            self.floor += (volume - self.floor) * FLOOR_SPEED_LOUD
        else:
            self.below += 1
            self.above = 0
            self.floor += (volume - self.floor) * FLOOR_SPEED_QUIET
        if not self.active and self.above >= (self.start_frames if self.start_frames is not None else START_FRAMES):
            self.active = True
            return True
        if self.active and self.below >= END_FRAMES:
            self.active = False
            return False
        return None


def enabled():
    return getattr(config, "VOICE_REACTION", True) is not False


async def stop_process(process):
    if process.returncode is None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
    try:
        await asyncio.wait_for(process.wait(), 3)
    except asyncio.TimeoutError:
        process.kill()


async def listen_once(on_change, should_listen, voice=None, on_command=None):
    """
    Reads the microphone until should_listen() is false or pw-record stops.
    Returns True if it stopped because it should (not a failure).
    voice (voice_commands.VoiceCommands): fed with the frames, on_command(name)
    awaited for each spoken command recognized.
    """
    if voice is not None:
        await asyncio.to_thread(voice.start)
    process = await asyncio.create_subprocess_exec(
        *RECORD_COMMAND, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, env=pipewire_env())
    detector = SoundDetector()
    # More sensitive: when the spoken commands listen
    voice_detector = SoundDetector(VOICE_RATIO, VOICE_MIN_LEVEL, VOICE_START_FRAMES)
    last_sent = 0.0
    try:
        while True:
            if not should_listen() or not enabled():
                return True
            try:
                data = await process.stdout.readexactly(FRAME_BYTES)
            except asyncio.IncompleteReadError:
                return False
            volume = level(data)
            change = detector.feed(volume)
            voice_detector.feed(volume)
            now = time.monotonic()
            if change is not None:
                last_sent = now
                await on_change(change)
            elif detector.active and now - last_sent >= KEEPALIVE_SECONDS:
                last_sent = now
                await on_change(True)
            if voice is not None and voice.ready:
                command = await asyncio.to_thread(voice.frame, data, voice_detector.active or detector.active)
                if command and on_command is not None:
                    await on_command(command)
    finally:
        await stop_process(process)
        if voice is not None:
            voice.stop()
        if detector.active:
            await on_change(False)


async def listen(on_change, should_listen, retry_delay=RETRY_DELAY, idle_delay=1, voice=None, on_command=None):
    """
    Listens to the microphone for the whole life of the agent, when
    should_listen() is true; on_change(active) is awaited at each change,
    on_command(name) for each spoken command (voice, see listen_once).
    """
    notice_shown = False
    while True:
        if not enabled() or not should_listen():
            await asyncio.sleep(idle_delay)
            continue
        try:
            stopped_on_purpose = await listen_once(on_change, should_listen, voice, on_command)
        except OSError as e:
            stopped_on_purpose = False
            if not notice_shown:
                print(f"⚠️ Microphone not listened to ({e})")
        if stopped_on_purpose:
            notice_shown = False
            continue
        if not notice_shown:
            print(f"ℹ️ No sound from the microphone, trying again every {retry_delay}s")
            notice_shown = True
        await asyncio.sleep(retry_delay)
