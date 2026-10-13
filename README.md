# CallTV — Raspberry Pi receiver

**English** | [Français](README.fr.md) | [Español](README.es.md)

The Raspberry Pi is plugged into the TV of the person being called. It runs **two
programs** that connect to the server with the same identity:

| Program | Role |
|---|---|
| **Python agent** (`main.py`) | Receives the call, plays the voice announcement, detects the button click, turns the TV on |
| **Chromium in kiosk mode** (`receveur.html`) | Shows the call, starts the camera and the microphone, sets up the video (WebRTC) |

> **This repository contains only the receiver.** The calls go through a server and a phone
> app that are not public: a Raspberry must be authorized on the server before it can receive
> calls. **To use the whole system, contact me** by opening an [issue](https://github.com/jgilles63/CallTV-Raspberry/issues).

## Hardware

- Raspberry Pi with a graphical environment (X11, display `:0`);
- **HDMI-CEC** compatible TV, with the Raspberry plugged into an HDMI input (**HDMI 3** by default, `HDMI_PORT` setting of `config.py`);
- **webcam with a microphone** (used by Chromium);
- **USB mouse** used as the "answer" button (inside a 3D-printed case);
- **USB speaker** for the ringtone (detected automatically: any model, any USB port); the
  sound of the call itself comes out of the TV (HDMI);
- Internet connection (server + Google text-to-speech).

## Files

| File | Role |
|---|---|
| `main.py` | Entry point: loads the identity, sets the volume to 100 %, starts the agent |
| `agent.py` | Core of the agent: WebSocket, incoming calls, mouse click, `SIGUSR1` signal, heartbeat |
| `config.py` | All the settings (**language**, server URL, paths, mouse, call duration, volumes) |
| `i18n.py` | Translations (fr, en, es): voice announcement, messages of the agent and of the setup scripts |
| `identity.py` | Reads `identity.json` (identifier + secret of the device) |
| `tts_audio.py` | Generates the voice announcement, mixes it with the ringtone, plays it |
| `tv_control.py` | Controls the TV through HDMI-CEC (`cec-client`) |
| `start_tv_control.sh` | Starts the agent in its Python virtual environment |
| `ringtone.mp3` | Ringtone: "game-music1" by Nia Mi ([OpenGameArt](https://opengameart.org/node/153251)), public domain (CC0); converted to `.wav` and repeated over the whole call |
| `ColdStart/setup_identity.py` | **Run once**: creates the device identity and a QR code |
| `ColdStart/identity_manager.py` | Creates, reads and resets the identity |
| `ColdStart/launch_chromium.sh` | Opens `receveur.html` full screen with the identity and language of the device |
| `ColdStart/chromium-autolaunch.service` | systemd service that starts Chromium at boot |
| `ColdStart/tv-control.service` | systemd service of the Python agent |
| `install.sh` | **Installation or update in one command** (see Installation) |
| `switch_server.sh` | Switches the Raspberry between the **production** server and the **test** server (see below) |
| `HomeAssistant/send_sigur_fromAlexa.sh` | Answers remotely by sending `SIGUSR1` to the agent |

## Language

One setting for the whole Raspberry: **`LANGUAGE` in `config.py`** (`"fr"`, `"en"` or
`"es"`). It changes:

- the **voice announcement**:

  | Language | Announcement |
  |---|---|
  | `fr` | "Hé mamie, c'est *name* qui t'appelle" |
  | `en` | "Hey grandma, it's *name* calling" |
  | `es` | "Oye abuela, es *name* quien te llama" |

- the user-facing messages of the agent and those of `setup_identity.py` (including the
  content of `setup_qr_code.txt`);
- the **TV screen**: `launch_chromium.sh` reads `LANGUAGE` and adds it to the address of
  `receveur.html` (`&lang=…`);
- the language of the messages the server sends to the agent.

After a change, restart the agent **and** the Chromium service. Announcements already cached
are not reused: the file name contains the language. The technical logs of the agent are in
English.

## How the agent works

1. **Connects** to `wss://appelermami.fr` and registers (`register_device`), with automatic
   reconnection and a heartbeat every 25 s.
2. **Incoming call** (`incoming_call`):
   - generates the announcement with **gTTS** in the configured language;
   - mixes it with the ringtone using **ffmpeg**, over 30 seconds;
   - caches the result in `cache_audio/` (one file per name and language, 30 files at most:
     the least recently used are deleted);
   - plays it with **aplay**. If the speech synthesis fails, only the ringtone is played.
3. **Answer**, by one of these three means:
   - a **left click** on the mouse (read with `evdev`, **detected automatically**: any model,
     any USB port, found again after being unplugged);
   - the **`SIGUSR1`** signal (`kill -USR1 <pid>`, see `HomeAssistant/`);
   - the **Answer** button of `receveur.html` (synchronized by the server).
4. **Turning the TV on** (`tv_control.py`): `on 0` to turn it on, then `as` (the Raspberry
   becomes the active source, port 3) repeated 5 times, because some TVs do not answer the
   first attempt.
5. **No answer** after 30 s: the agent hangs up (`no_answer`).

The camera is **not** handled by Python: `receveur.html` starts it when the call is answered.
- **Call from one's own TV**: on order of the server (`outgoing_call_start`), the agent turns the TV on, on the Raspberry input, without ringtone, and gives it back at the end of the call. During this call, the mouse does not hang up (the phone does).

## Installation

### Automatic installation (recommended)

1. **SD card**: with [Raspberry Pi Imager](https://www.raspberrypi.com/software/), write
   **Raspberry Pi OS with desktop** (64-bit). In the Imager settings: user name and password
   (your choice), Wi-Fi, **SSH enabled**, and optionally a host name.
2. **Copy this folder** `Raspberry_receiver` to the Raspberry, from a PC:
   ```bash
   scp -r Raspberry_receiver USER@PI_ADDRESS:~/
   ```
3. **Run the script** over SSH, as the Raspberry user (not with `sudo`):
   ```bash
   cd ~/Raspberry_receiver
   bash install.sh            # asks the language (fr / en / es)
   bash install.sh --lang en  # or without the question
   ```

The script does everything described in steps 1 to 8 below: system packages, Python
environment, ringtone conversion, language, user rights (mouse, TV, sound), device identity,
automatic start services (agent and Chromium), desktop autologin, no screen blanking, camera
and microphone allowed in Chromium. At the end it shows **the identifier and the QR code** to
have authorized by the server administrator (step 6), then offers to reboot.

It can be **run again at any time to update** the Raspberry: the identity (`identity.json`)
and the settings of `config.py` are kept (a copy of the old `config.py` is kept). A log is
written to `~/appelermamie-install.log`.

### Manual installation (step by step)

All the files are deployed **flat** in `~/AppelerMamie/`, i.e. the home folder of the
Raspberry user (including the content of `ColdStart/`). The scripts find this folder
automatically; only `chromium-autolaunch.service` must be edited (replace `YOUR_USER`).

### 1. System packages

```bash
sudo apt install ffmpeg alsa-utils cec-utils chromium python3-venv
```

### 2. Python environment

```bash
cd ~/AppelerMamie
python3 -m venv venv
source venv/bin/activate
pip install websockets evdev gTTS qrcode
```

### 3. Ringtone in WAV format

`aplay` plays WAV files: convert the ringtone once (`install.sh` converts every `.mp3`
of the folder). It lasts a few seconds: the agent repeats it over the whole call.

```bash
ffmpeg -i ringtone.mp3 ringtone.wav
```

### 4. Language

Choose the language in `config.py` **before** the next step (the messages of
`setup_identity.py` use it):

```python
LANGUAGE = "en"   # "fr", "en" or "es"
```

### 5. Device identity

```bash
python3 setup_identity.py
```

The script creates:

- `identity.json` (permissions `600`): identifier `rpi-xxxxxxxx` and **secret** of the device;
- `setup_qr_code.txt`: QR code of the identifier, to scan from the mobile app.

> ⚠️ `identity.json` contains the device secret: never share it or commit it.
> To show or reset the identity: `python3 identity_manager.py --show` / `--reset`.

### 6. Authorization on the server

The server only accepts Raspberry devices added by its administrator. Send them **the
identifier** (`rpi-xxxxxxxx`) **and the verification code** (`XXXX-XXXX-XXXX`), shown at
the end of the installation and in `setup_qr_code.txt` — never the secret — for example by opening an [issue on the GitHub repository](https://github.com/jgilles63/CallTV-Raspberry/issues).

Meanwhile:

- the agent shows a "THIS RASPBERRY IS NOT AUTHORIZED ON THE SERVER YET" message with the
  identifier, the code and the administrator contact, then retries every 30 s;
- the TV screen shows the same message and retries too.

As soon as the administrator has added the device, the agent and then the screen connect on
their own, without a restart. The server then pins the device secret.

> The code is computed from the secret: it proves to the administrator that the request
> really comes from this Raspberry. To see it again: `python3 identity_manager.py --show`.

> If the identity is reset (`--reset`), the Raspberry gets a **new identifier** that must be
> authorized again.

### 7. Settings to check in `config.py`

| Setting | Current value | To check |
|---|---|---|
| `LANGUAGE` | `fr` | Language of the Raspberry (`fr`, `en`, `es`) |
| `SERVER_URL` | `wss://appelermami.fr` | Address of your server |
| `MOUSE_DEVICE` | `None` (automatic detection) | Only set it to force a specific device (several mice plugged in): stable path from `ls -l /dev/input/by-id/` |
| `AUDIO_DEVICE` | `None` (automatic detection) | Ringtone speaker: the first USB speaker found. Only set it to force a specific card (name between brackets in `aplay -l`) |
| `MOUSE_RETRY_DELAY` | `5` | Delay between two searches for the mouse when it is missing (seconds) |
| `HDMI_PORT` | `3` | HDMI input of the TV the Raspberry is plugged into (the TV switches to it when a call is accepted). Check: `echo "scan" \| cec-client -s -d 1` shows the Raspberry at address `3.0.0.0` for input 3 |
| `RINGTONE_PATH` | `~/AppelerMamie/ringtone.wav` | Another ringtone: copy its `.mp3` into `~/AppelerMamie`, run `install.sh` again (it makes the `.wav`), then give the path of the `.wav` here. Kept by `install.sh`; if the file is missing, the ringtone of the project is played |
| `CALL_DURATION` | `30` | Ringing time before giving up (seconds) |
| `MAX_CACHED_CALLS` | `30` | Number of audio files kept in cache |
| `UNAUTHORIZED_RETRY_DELAY` | `30` | Delay between two attempts while the server refuses the device |

The user running the agent must be able to read the mouse (`input` group).

### 8. Starting

In normal operation, both programs start automatically with the Raspberry:

- **the Python agent** runs as a service (it runs `start_tv_control.sh`);
- **Chromium** is started by `chromium-autolaunch.service`.

```bash
# Manual test of the agent
./start_tv_control.sh

# Install the Chromium service (after replacing YOUR_USER)
sudo cp chromium-autolaunch.service /etc/systemd/system/
sudo systemctl enable --now chromium-autolaunch.service
```

> The service of the Python agent is `ColdStart/tv-control.service` (replace `YOUR_USER`,
> which `install.sh` does). It must run as the Raspberry user (not `root`), otherwise
> `~/AppelerMamie` does not point to the right folder.

## Production or test server

During development, a copy of the server runs separately (`wss://appelermami.fr:8443`) so
that the server used by the family is never touched. A single setting chooses the server:
`SERVER_URL` in `config.py`, used by the agent **and** by the TV screen
(`launch_chromium.sh` reads it). To switch:

```bash
bash ~/AppelerMamie/switch_server.sh          # shows the current server
bash ~/AppelerMamie/switch_server.sh test     # test server
bash ~/AppelerMamie/switch_server.sh prod     # production server
```

The agent and the TV screen restart by themselves. `install.sh` keeps this setting when it
is run again. On the test server, the Raspberry no longer receives the calls of the normal
app (only those of a test APK or of `https://appelermami.fr:8443/appelant.html`).

## Automatic tests

The [`tests/`](tests/) folder checks the agent, the self-repair, the health report, the
ringtone speaker, the mouse, the HDMI input and `install.sh` (run in a fake home), **without
a Raspberry**: system files, commands, the TV and the network are simulated. They run on a
PC (Linux, or Windows with Git Bash) and are not copied to the Pi by `install.sh`.

```bash
cd Raspberry_receiver
pip install "websockets>=13,<18"
python3 tests/run_tests.py            # all the tests
python3 tests/run_tests.py selfheal   # only the files whose name contains "selfheal"
```

GitHub also runs them on every push.

## Troubleshooting

| Problem | Hint |
|---|---|
| "NOT AUTHORIZED ON THE SERVER YET" | Send the identifier to the server administrator (see step 6) |
| "THE SERVER REFUSES THE SECRET" | `identity.json` changed: ask the administrator to remove and authorize the identifier again |
| No ringtone | Agent logs: at startup, "Ringtone speaker: …" shows the speaker found; "No USB speaker found" means no USB speaker is detected (the ringtone then goes through the TV, only heard if it is on). Check the connection with `aplay -l` |
| The click does not answer | Agent logs: look for "Mouse found" or "No mouse found". Check the permissions on `/dev/input/` (`input` group) and, if several mice are plugged in, force the right one with `MOUSE_DEVICE` |
| The TV does not switch | `echo "scan" \| cec-client -s -d 1` to check CEC |
| No voice announcement | gTTS needs Internet; only the ringtone is played as a fallback |
| The TV screen is in the wrong language | Check `LANGUAGE` in `config.py`, then restart the Chromium service |
| A `.sh` script fails with `\r` | Windows line endings: `sed -i 's/\r$//' script.sh` |
