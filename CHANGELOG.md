# Changelog

Every published version of the Raspberry part (this repository), newest
first: what is different from the version before, exhaustively — new
features, changes, fixes, settings of `config.py`, what an update does to an
installed Raspberry, and the tests. Dates are those of the signed tags.

Features of the TV page (`receveur.html`, `ecran.html`) are served by the
server, not by this repository: they are listed here only where the
Raspberry part takes part in them.

How to update a Raspberry: from the server (`admin.js update <id> <version>`),
or by hand (`git -C ~/AppelerMamie-src fetch --tags && git -C ~/AppelerMamie-src checkout <version> && bash ~/AppelerMamie-src/install.sh --update`).
An update keeps the identity, `config.py` (settings listed as kept) and the
settings changed on the TV.

---

## v0.4.0 — 23/10/2026

**Second screen next to the TV.** A screen (a 7" touch screen is aimed at)
plugged on the second micro-HDMI of the Pi shows its own page, kept in step
with the TV page. With one screen, nothing changes.

### New
- **Second screen detection** (`display_mode.py`):
  - `TV_OUTPUT = "HDMI-A-1"` (the micro-HDMI next to the power socket: always
    the TV) and `SECOND_OUTPUT = "HDMI-A-2"`;
  - `second_screen()` gives the size of the screen on HDMI-A-2 only when the
    TV on HDMI-A-1 is there too (a TV plugged alone on HDMI-A-2 is one screen:
    no change), `None` otherwise or when `SECOND_SCREEN = False`;
  - `python3 display_mode.py --second` prints that size (`1024x600`), exit 1
    without a second screen (used by `launch_chromium.sh`);
  - a second screen wider than 1920 pixels is set to 1920 x 1080, like the TV.
- **Kiosk with two windows** (`ColdStart/launch_chromium.sh`): the TV page as
  before, then, with a second screen, the touch page
  `https://<server>/ecran.html?id=<id>&lang=<lang>` opened as an "app" window
  of the same Chromium (`--app`, same profile: the two pages talk through
  BroadcastChannel, never through the server). **The secret of the Raspberry
  is never given to the touch page.** The service lives as long as the first
  window.
- **labwc settings written by `install.sh`** in `~/.config/labwc/rc.xml`
  (merged with the ones of the system, labwc runs with `-m`; added once, the
  rest of the file kept; the desktop reads them again):
  - `<windowRule identifier="*ecran*">` → `MoveToOutput HDMI-A-2` (the window
    of the touch page goes to the second screen; no `ToggleFullscreen`, the
    kiosk already makes it fullscreen);
  - `<touch mapToOutput="HDMI-A-2"/>` (the touches of a touch screen land on
    the second screen only, never over the whole desktop).
- **Plugged or unplugged while running** (`agent.py`): checked every 30 s
  (`check_second_screen`); the kiosk is restarted so that it opens the right
  windows (`restart_kiosk`: Chromium of the user stopped, systemd starts it
  again), outside a ringing call or a call only — otherwise at the first check
  after it; plugged then unplugged during a call: nothing to do.
- **Health report** (`diagnostics.py`, `admin.js diagnose`): line "Second
  screen (touch)": `HDMI-A-2: 1024x600`, or `-` (fr / en / es in `i18n.py`).

### Changed
- **The answer button is never a touch screen** (`agent.py`, `find_mouse`):
  a device that points directly on a screen (`INPUT_PROP_DIRECT`) is never
  taken as the mouse of the person, even if it sends a left button; a finger
  answers only with the "Answer" button of the touch page. Touchpads are
  still used when no mouse is plugged, as before.
- **Sound never on the second screen**:
  - `call_audio.py`: with a second screen, only the HDMI card of the TV
    (`vc4hdmi0`, `TV_CARD_ID`) is used for the call sound — even while the TV
    wakes up and has no sound yet (the existing retry waits for it);
  - `tts_audio.py`: ringtone without USB speaker and with a second screen:
    the HDMI output of the TV is made the default output first
    (`call_audio.tv_hdmi_as_default`);
  - one screen, on either micro-HDMI: as before.

### Settings (`config.py`)
- `SECOND_SCREEN = "auto"` (new, kept by updates): `"auto"` = a screen on
  HDMI-A-2 shows the touch page; `False` = never.

### Update of an installed Raspberry
- `install.sh --update` adds the two labwc lines above once; nothing else
  changes on a Raspberry with one screen.

### Hardware
- Tried on a Pi 4 with 2 GB and a computer screen (1920 x 1080) on HDMI-A-2:
  everything works, but a video call lags (85 °C, processor slowed down by the
  heat, swap used). **A Pi with 4 GB and a fan are advised.** Pi 5: same
  principle, not tested. A real touch screen and a screen unplugged during a
  call are still to be tried.

### Tests
- New `tests/second_screen_test.py` (plugged / unplugged, during a ringing
  call, a call, a call made from this TV, kiosk that cannot be restarted).
- `display_mode_test.py` (second screen, TV alone on HDMI-A-2, disabled
  outputs, `SECOND_SCREEN = False`, `--second`, health line),
  `mouse_test.py` (touch screen alone, with a touchpad, with a mouse),
  `call_audio_test.py` and `audio_test.py` (TV + second screen, TV waking
  up, one screen on HDMI 1), `install_test.sh` (labwc rule and touch line
  added once, own labwc settings kept, `SECOND_SCREEN` kept).
- `hdmi_test.py`, `settings_test.py`: example names only (no personal name).

---

## v0.3.0 — 23/10/2026

### New
- **Quiet hours** (`config.py`: `QUIET_START_HOUR = 22`, `QUIET_END_HOUR = 8`,
  kept by updates): during them, a call received is shown on the TV page and
  answered with the button as usual, but **without ringtone nor voice
  announcement** (`agent.py`, local time of the Raspberry, over midnight;
  same hour twice = always rings). Changed on the settings page of the TV
  (`settings_store.py`: `quietStart` / `quietEnd`, 0 to 23, no restart of
  the agent); `install.sh` writes them back into `config.py`.

---

## v0.2.9 — 19/10/2026

### New
- **Name of this TV** (`config.py`: `TV_NAME`, kept by updates; settings page
  of the TV): sent at registration; the other TVs show this name in their
  contacts and history, "Robot, appelle <name>" uses it, and it is announced
  when this TV calls.

---

## v0.2.8 — 19/10/2026

### New
- **Radio page support**: levels of the sound measured between ffmpeg and
  aplay (wave of the radio page), volume of the radio set in real time from
  the page (`radio_request`, `radio_play`, `radio_stop`, `radio_volume`,
  `radio_watch`).
- **Stations of the country of the TV** (`radio_stations.py`: France, Spain,
  United Kingdom, Portugal, Mexico, United States; streams checked on a Pi);
  `install.sh` replaces the former Paris list by the list of the country.

### Changed
- **Separate volumes**: radio (0-100 %) and voice of the robot (1-10), kept
  apart from the two ringtone volumes, all four on the settings page.
- **Voice commands**: the wake word must be sure in a command too, and the
  command must be nearly the whole sentence (fewer commands nobody asked);
  `voice.log` keeps what the robot heard and did.
- **Weather said by the robot** according to the time of day (the rest of the
  day, or tomorrow in the evening).

---

## v0.2.7 — 18/10/2026

### New
- **The robot reacts to voices** (`sound_level.py`, `VOICE_REACTION`): only
  the volume of the camera microphone is measured outside calls (nothing
  recorded); the robot of the TV page walks when someone speaks.
- **Weather of the home screen**: place of the Raspberry (`WEATHER_CITY`,
  `WEATHER_POSTCODE`, `WEATHER_COUNTRY`, asked by `install.sh`, options
  `--city`, `--postcode`, `--country`) sent at registration; health line.
- **Spoken commands** (`voice_commands.py`, offline Vosk recognition with a
  closed grammar, fr / en / es; model installed by `install.sh` with a
  pinned SHA-256; wake word "robot"): hello, time, weather, "how are you"
  (health report said), radio by name or frequency (`radio.py`), volume, call
  a TV contact, answer / decline while it rings; answers said on the speaker
  (`robot_answers.py`).
- **Settings page of the TV** (`settings_store.py`, `settings.json`):
  language, ringtone volumes (music, voice), place of the weather; speech
  model of a new language downloaded (`voice_model.py`); the agent restarts
  itself when needed.
- **Calendar of the TV** (`calendar_store.py`, `calendar.json`): notes of the
  days (every year optional), kept on the Raspberry only.

---

## v0.2.6 — 17/10/2026

### New
- **Remote control of the TV through HDMI-CEC** (`remote_keys.py`): the keys
  (arrows, OK, Back) go to the TV page; while it rings OK answers and Back
  declines; during a received call Back hangs up.
- **1080p screen** (`display_mode.py`, `SCREEN_MODE = "1080p"`): a 4K TV is
  set to 1920 x 1080 up to 60 Hz (smoother video calls), at Chromium start
  and every 30 s.

### Changed
- `tv_control.py` uses `cec-ctl` (kernel CEC) instead of `cec-client`, which
  cleared the CEC configuration and caused "errno=16" errors during calls;
  the Raspberry stays declared to the TV as a playback device (checked every
  30 s); the input is the physical address given by the TV (`HDMI_PORT` only
  when it gives none).

---

## v0.2.5 — 17/10/2026

### Fixed
- Health report run by hand (`diagnose.sh`): "Wi-Fi power saving" showed `-`
  (`iw` is in `/usr/sbin`, not in the user `PATH`).

---

## v0.2.4 — 15/10/2026

### Fixed
- Health report: the output of the call sound showed `?` (default output read
  from the top-level props of the PipeWire metadata).

---

## v0.2.3 — 15/10/2026

### New
- **Call sound on the TV** (`call_audio.py`, `CALL_AUDIO_OUTPUT = "auto"`,
  `"hdmi"` or `"usb"`, kept by updates): a TV answering HDMI-CEC and
  accepting sound gets the call sound (HDMI output turned back on if
  PipeWire left it off), otherwise the USB speaker; the ringtone stays on
  the USB speaker. Health line: output of the call sound.

---

## v0.2.2 — 14/10/2026

### New
- **Watchdog of the TV page during a call**: the page frozen after an accept
  (no camera) is reported by the server (`display_stuck`); the agent writes it
  for `selfheal.py`, which restarts Chromium once the call is over (at most
  every 10 minutes). The accepted call is remembered until its hangup, so
  that the self-repair never acts during a conversation.

---

## v0.2.1 — 13/10/2026

### Changed
- The agent startup log shows the installed version.

---

## v0.2.0 — 13/10/2026

### New
- **Remote updates to signed versions** (`update.sh`,
  `appelermamie-update.service` and `.path`, key in
  `/etc/appelermamie/allowed_signers`): started when the agent receives an
  update request from the server; waits for the end of a call; accepts only
  a tag signed by the project key and newer than the installed one; installs
  it with `install.sh --update`; goes back to the previous version if the
  agent does not connect again. Result in `update.json`; version sent at
  registration and shown in the health report.
- `install.sh --update`: no question, system packages only when their list
  changed, no reboot.

---

## v0.1.2 — 13/10/2026

### New
- **Greeting of the call announcement** (`GREETING_NAME`, asked at the first
  installation, option `--greeting`, kept by updates): "Hey <greeting>, it's
  Paul calling", or "It's Paul calling" without it.
- Installation from this public repository (`git clone` + `install.sh`).

---

## v0.1.0 — 13/10/2026

First public version (MIT): the agent of the Raspberry (calls, mouse
button, voice announcement, HDMI-CEC, self-repair, health report), the
installation script and the tests. Free default ringtone (`ringtone.mp3`,
"game-music1" by Nia Mi, CC0); without voice announcement the ringtone is
repeated over the whole call.
