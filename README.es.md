# CallTV — Receptor Raspberry Pi

[English](README.md) | [Français](README.fr.md) | **Español**

La Raspberry Pi está conectada al televisor de la persona que recibe la llamada. Ejecuta
**dos programas** que se conectan al servidor con la misma identidad:

| Programa | Función |
|---|---|
| **Agente Python** (`main.py`) | Recibe la llamada, reproduce el anuncio de voz, detecta el clic del botón, enciende el televisor |
| **Chromium en modo quiosco** (`receveur.html`) | Muestra la llamada, activa la cámara y el micrófono, establece el vídeo (WebRTC) |

> **Este repositorio contiene solo el receptor.** Las llamadas pasan por un servidor y una
> aplicación de teléfono que no son públicos: una Raspberry debe estar autorizada en el servidor
> antes de poder recibir llamadas. **Para usar el conjunto, contáctame** abriendo una
> [issue](https://github.com/jgilles63/CallTV-Raspberry/issues).

## Hardware

- Raspberry Pi con entorno gráfico (X11, pantalla `:0`);
- televisor compatible con **HDMI-CEC**, con la Raspberry conectada a una entrada HDMI (la entrada se lee en el propio televisor; `HDMI_PORT` de `config.py` solo si el televisor no la da);
- **webcam con micrófono** (usada por Chromium);
- **ratón USB** que sirve de botón para «responder» (dentro de una carcasa impresa en 3D);
- **altavoz USB** para el tono de llamada (detectado automáticamente: cualquier modelo, cualquier
  puerto USB); el sonido de la llamada sale por el televisor (HDMI) si es un televisor que
  responde por HDMI-CEC, si no por el altavoz USB (monitor de ordenador sin sonido);
- conexión a Internet (servidor + síntesis de voz de Google).

Probado (15/10/2026, instalación completa desde una tarjeta SD vacía) en una **Raspberry Pi 4
Model B** con **Raspberry Pi OS de 64 bits con escritorio** (Debian 13 «trixie»), Chromium 154,
una webcam USB con micrófono, un altavoz USB y un ratón inalámbrico. Una pantalla sin HDMI-CEC
también funciona: solo hay que encenderla a mano (el diagnóstico muestra «TV vista por
HDMI-CEC: unknown»).

## Archivos

| Archivo | Función |
|---|---|
| `main.py` | Punto de entrada: carga la identidad, pone el volumen al 100 %, inicia el agente |
| `agent.py` | Núcleo del agente: WebSocket, llamadas entrantes, clic del ratón, señal `SIGUSR1`, heartbeat |
| `config.py` | Todos los ajustes (**idioma**, URL del servidor, rutas, ratón, duración de llamada, volúmenes) |
| `i18n.py` | Traducciones (fr, en, es): anuncio de voz, mensajes del agente y de los scripts de instalación |
| `identity.py` | Lee `identity.json` (identificador + secreto del dispositivo) |
| `tts_audio.py` | Genera el anuncio de voz, lo mezcla con el tono y lo reproduce |
| `tv_control.py` | Controla el televisor mediante HDMI-CEC (`cec-ctl` del núcleo Linux): lo enciende, cambia su entrada, pregunta su estado; mantiene la Raspberry declarada al televisor como reproductor |
| `remote_keys.py` | **Mando del televisor** por HDMI-CEC: el núcleo convierte sus teclas en un teclado (`vc4-hdmi-0`), leído por el agente: flechas, OK, Volver |
| `call_audio.py` | Elige la salida del sonido de la llamada: el televisor (HDMI) o el altavoz USB |
| `display_mode.py` | **Resolución de la pantalla**: un televisor 4K pasa a 1920 × 1080 (hasta 60 Hz), mucho más ligero para la Raspberry Pi 4 durante una videollamada; las pantallas de 1920 píxeles o menos nunca se cambian (`wlr-randr`) |
| `sound_level.py` | **Robot que reacciona a los sonidos**: fuera de las llamadas, mide solo el **volumen** del micrófono de la cámara (`pw-record`, compartido con Chromium; no se graba ni se envía nada) y avisa a la página de la TV cuando alguien habla (`sound_activity`): su robot cruza la pantalla de un lado a otro |
| `voice_commands.py` | **Órdenes de voz al robot**: «Robot hola» (o «Hola robot») hace que el robot de la página de la TV salude con la mano y responda «Hola, soy Robot» en el altavoz; «Robot, qué hora es» y «Robot, qué tiempo hace»: gafas e índice levantado en la TV, la hora o el tiempo del día dichos en voz alta. «Robot» solo: los ojos y la boca del robot se ponen verdes unos segundos, basta entonces con la pregunta. También la radio, el volumen y la llamada a un contacto de TV (`radio.py`); mientras suena, «Robot, contesta» / «Robot, cuelga» (el timbre baja mientras el robot escucha). Reconocido en la propia Raspberry (Vosk, modelo pequeño del idioma en `~/AppelerMamie/vosk-model`, lista cerrada de palabras), solo cuando se oye un sonido; modelo descargado durante las llamadas Contra las órdenes que nadie pidió: la palabra de activación debe ser segura también en una orden (confianza 0,8) y la orden debe ser casi toda la frase oída (2 palabras más como máximo); lo que el robot oyó e hizo se guarda en `voice.log` (300 últimas líneas, guardadas tras un reinicio; solo las palabras de las órdenes). |
| `robot_answers.py` | Frases del robot: la hora («Son las 2 y 35»), el tiempo (temperatura actual y previsión del día, pedidas al servidor) y su salud («Robot, cómo estás»: el informe de `diagnostics.py`, lo que falla o hay que vigilar, temperatura, memoria y disco libres, tiempo encendido), en el idioma de la Raspberry |
| `radio.py` | **Radio pedida por voz**: «Robot, pon la radio» (última emisora), «Robot, radio 101.2» (emisora de esa frecuencia), «Robot, pon Nostalgie» (su nombre), «Robot … para» o el botón Stop de la página de la TV; encendida al volumen 2, bajada a 1 mientras el robot escucha; emisoras de `config.py` (`RADIO_STATIONS`), flujo leído por ffmpeg y tocado en el altavoz USB; bajada mientras el robot escucha, en pausa mientras habla, cortada por una llamada o el botón. También «Robot, volumen 1 a 10» (robot y radio; el timbre sigue al 100 %) y «Robot, llama a <contacto de TV>» (la llamada sale de este televisor) La **página de la radio de la TV** también elige, pone y para una emisora; el sonido pasa de ffmpeg a aplay por el agente, que mide su nivel cada 50 ms para la onda dibujada en esa página. |
| `radio_stations.py` | **Emisoras de cada país**: 10 a 12 grandes emisoras de Francia (París), España (Madrid), Reino Unido (Londres), Portugal (Lisboa), México (Ciudad de México) y Estados Unidos (Nueva York), flujos comprobados en una Pi el 19/10/2026; el país de los ajustes se reconoce en francés, inglés, español y portugués («Espagne», «España», «Spain»), si no el idioma de la tele |
| `settings_store.py` / `voice_model.py` | **Ajustes cambiados en la TV** (engranaje de la pantalla de inicio): `settings.json`, una lista cerrada (idioma, volumen del timbre, lugar del tiempo), cada valor comprobado, aplicada al final de `config.py`; `install.sh` los vuelve a escribir en `config.py` y borra el archivo. Un nuevo idioma recibe su modelo de voz (mismo SHA-256 que `install.sh`) |
| `calendar_store.py` | **Calendario de la TV** (clic u OK en la hora de la pantalla de inicio): notas de los días (texto libre, opcionalmente cada año) guardadas solo en la Raspberry, en `calendar.json` (cada nota comprobada: fecha real, texto limpiado y cortado a 80, 300 notas como máximo); el servidor solo las transmite a la página de la TV |
| `start_tv_control.sh` | Inicia el agente en su entorno virtual de Python |
| `ringtone.mp3` | Tono: «game-music1» de Nia Mi ([OpenGameArt](https://opengameart.org/node/153251)), dominio público (CC0); convertido a `.wav` y repetido durante toda la llamada |
| `ColdStart/setup_identity.py` | **Ejecutar una vez**: crea la identidad del dispositivo y un código QR |
| `ColdStart/identity_manager.py` | Crea, lee y reinicia la identidad |
| `ColdStart/launch_chromium.sh` | Abre `receveur.html` a pantalla completa con la identidad y el idioma del dispositivo |
| `ColdStart/chromium-autolaunch.service` | Servicio systemd que inicia Chromium al arrancar |
| `ColdStart/tv-control.service` | Servicio systemd del agente Python |
| `install.sh` | **Instalación o actualización con un solo comando** (ver Instalación) |
| `selfheal.py` | Reparación automática (Wi-Fi, página de la TV desconectada o bloqueada durante una llamada, agente, reinicio nocturno), como root cada minuto |
| `diagnostics.py`, `diagnose.sh` | Informe de estado (pedido también por el servidor: `node admin.js diagnose`) |
| `update.sh` | **Actualización a distancia** a una versión firmada (ver «Actualizaciones a distancia») |
| `ColdStart/allowed_signers` | Clave pública que firma las versiones (instalada una vez en la Raspberry) |
| `switch_server.sh` | Cambia la Raspberry entre el servidor de **producción** y el servidor de **prueba** (ver más abajo) |
| `HomeAssistant/send_sigur_fromAlexa.sh` | Responde a distancia enviando `SIGUSR1` al agente |

## Idioma

Un solo ajuste para toda la Raspberry: **`LANGUAGE` en `config.py`** (`"fr"`, `"en"` o
`"es"`). Cambia:

- el **anuncio de voz**:

  | Idioma | Anuncio (con `GREETING_NAME = "abuela"`) | Sin saludo (`None`) |
  |---|---|---|
  | `fr` | «Hé abuela, c'est *nombre* qui t'appelle» | «C'est *nombre* qui t'appelle» |
  | `en` | «Hey abuela, it's *nombre* calling» | «It's *nombre* calling» |
  | `es` | «Oye abuela, es *nombre* quien te llama» | «Es *nombre* quien te llama» |

  El saludo (`GREETING_NAME`: abuela, abuelo, mamá, papá, un nombre…) lo pregunta
  `install.sh` en la primera instalación (opción `--greeting`);

- los mensajes del agente destinados al usuario y los de `setup_identity.py` (incluido el
  contenido de `setup_qr_code.txt`);
- la **pantalla del televisor**: `launch_chromium.sh` lee `LANGUAGE` y lo añade a la dirección
  de `receveur.html` (`&lang=…`);
- el idioma de los mensajes que el servidor envía al agente.

Después de un cambio, reinicia el agente **y** el servicio Chromium. Los anuncios ya guardados
en caché no se reutilizan: el nombre del archivo contiene el idioma. Los registros técnicos
del agente están en inglés.

## Funcionamiento del agente

1. **Se conecta** a `wss://appelermami.fr` y se registra (`register_device`), con reconexión
   automática y un heartbeat cada 25 s.
2. **Llamada entrante** (`incoming_call`):
   - genera el anuncio con **gTTS** en el idioma configurado;
   - lo mezcla con el tono mediante **ffmpeg**, durante 30 segundos;
   - guarda el resultado en caché en `cache_audio/` (un archivo por nombre e idioma, 30
     archivos como máximo: se borran los usados hace más tiempo);
   - lo reproduce con **aplay**. Si la síntesis falla, solo se reproduce el tono.
3. **Respuesta**, de una de estas tres formas:
   - un **clic izquierdo** del ratón (leído con `evdev`, **detectado automáticamente**: cualquier
     modelo, cualquier puerto USB, se vuelve a encontrar después de desconectarlo);
   - la señal **`SIGUSR1`** (`kill -USR1 <pid>`, ver `HomeAssistant/`);
   - el botón **Responder** de `receveur.html` (sincronizado por el servidor);
   - **OK en el mando del televisor**, cuando el televisor muestra la entrada de la Raspberry
     (Volver rechaza; durante la llamada, Volver cuelga).
4. **Encendido del televisor** (`tv_control.py`, `cec-ctl`): `--image-view-on` para encenderlo
   y después `--active-source` (la Raspberry pasa a ser la fuente activa, dirección dada por el
   televisor, p. ej. `3.0.0.0` para la entrada 3) repetido 5 veces, porque algunos televisores
   no responden al primer intento. Entre medias, `--give-device-power-status` pregunta el
   estado del televisor: si un televisor responde y acepta sonido (ELD), el sonido de la llamada sale por el
   televisor (`call_audio.py` vuelve a activar la salida HDMI si PipeWire la apagó porque el
   televisor estaba en espera al arrancar la Pi); si no, sale por el altavoz USB. El tono y el
   anuncio siempre siguen en el altavoz USB.
5. **Sin respuesta** después de 30 s, el agente cuelga (`no_answer`).

La cámara **no** la gestiona Python: la activa `receveur.html` en el momento de responder.
- **Llamada desde su TV**: por orden del servidor (`outgoing_call_start`), el agente enciende la TV en la entrada de la Raspberry, sin timbre, y la devuelve al final de la llamada. Durante esta llamada, el ratón no cuelga (se cuelga desde el teléfono).

## Instalación

### Instalación automática (recomendada)

1. **Tarjeta SD**: con [Raspberry Pi Imager](https://www.raspberrypi.com/software/), escribir
   **Raspberry Pi OS con escritorio** (64 bits). En los ajustes de Imager: nombre de usuario y
   contraseña (a elegir), Wi-Fi, **SSH activado** y, si se quiere, un nombre de equipo.
2. **Descargar el proyecto** en la Raspberry (por SSH, con el usuario de la Raspberry),
   eligiendo una versión publicada (lista: «Releases» / «Tags» del repositorio):
   ```bash
   git clone https://github.com/jgilles63/CallTV-Raspberry.git ~/AppelerMamie-src
   cd ~/AppelerMamie-src
   git checkout v0.2.8        # la última versión (ver «Releases»)
   ```
   (`sudo apt install -y git` si falta git.) Esta carpeta solo contiene el proyecto
   descargado: el script instala los programas en `~/AppelerMamie`.
3. **Ejecutar el script**, con el usuario de la Raspberry (no con `sudo`):
   ```bash
   bash install.sh            # pregunta el idioma (fr / en / es)
   bash install.sh --lang es  # o sin pregunta
   ```
   En la primera instalación, también pregunta cómo el anuncio de voz llama a la persona
   («Oye abuela, es Paul quien te llama», o «papá», un nombre, o nada).

El script lo hace todo, no hay nada más que instalar ni copiar:

- instala los **paquetes del sistema** (ffmpeg, v4l-utils para `cec-ctl`, Chromium…) y el **entorno
  Python**;
- **copia los programas** en `~/AppelerMamie` y convierte el tono;
- configura el idioma, los permisos del usuario (ratón, TV, sonido), crea la **identidad** del
  dispositivo;
- instala y **arranca** los servicios (agente, Chromium en la TV, reparación automática), el
  inicio de sesión automático en el escritorio, la pantalla sin reposo, la cámara y el
  micrófono permitidos en Chromium.

Al final muestra **el identificador y el código de verificación** que el administrador del
servidor debe autorizar (paso 6) y propone reiniciar.

**Actualizar** a una versión más reciente: la identidad (`identity.json`) y los ajustes de
`config.py` se conservan (se guarda una copia del `config.py` anterior). Se escribe un
registro en `~/appelermamie-install.log`.

```bash
cd ~/AppelerMamie-src
git fetch --tags
git checkout v0.2.0          # la nueva versión
bash install.sh
```

### Instalación manual (paso a paso)

Todos los archivos se despliegan **en una misma carpeta**, `~/AppelerMamie/`, es decir, la
carpeta personal del usuario de la Raspberry (incluido el contenido de `ColdStart/`). Los
scripts encuentran esta carpeta automáticamente; solo hay que editar
`chromium-autolaunch.service` (sustituir `YOUR_USER`).

### 1. Paquetes del sistema

```bash
sudo apt install ffmpeg alsa-utils v4l-utils cec-utils chromium python3-venv
```

### 2. Entorno de Python

```bash
cd ~/AppelerMamie
python3 -m venv venv
source venv/bin/activate
pip install websockets evdev gTTS qrcode
```

### 3. Tono en formato WAV

`aplay` reproduce archivos WAV: convierte el tono una vez (`install.sh` convierte todos los
`.mp3` de la carpeta). Dura unos segundos: el agente lo repite durante toda la llamada.

```bash
ffmpeg -i ringtone.mp3 ringtone.wav
```

### 4. Idioma

Elige el idioma en `config.py` **antes** del paso siguiente (los mensajes de
`setup_identity.py` lo usan):

```python
LANGUAGE = "es"   # "fr", "en" o "es"
```

### 5. Identidad del dispositivo

```bash
python3 setup_identity.py
```

El script crea:

- `identity.json` (permisos `600`): identificador `rpi-xxxxxxxx` y **secreto** del dispositivo;
- `setup_qr_code.txt`: código QR del identificador, para escanearlo desde la aplicación móvil.

> ⚠️ `identity.json` contiene el secreto del dispositivo: nunca lo compartas ni lo subas al
> repositorio. Para mostrar o reiniciar la identidad:
> `python3 identity_manager.py --show` / `--reset`.

### 6. Autorización en el servidor

El servidor solo acepta las Raspberry añadidas por su administrador. Envíale **el
identificador** (`rpi-xxxxxxxx`) **y el código de verificación** (`XXXX-XXXX-XXXX`), que se
muestran al final de la instalación y en `setup_qr_code.txt` —nunca el secreto—, por ejemplo abriendo una [issue en el repositorio de GitHub](https://github.com/jgilles63/CallTV-Raspberry/issues).

Mientras tanto:

- el agente muestra un mensaje «ESTA RASPBERRY AÚN NO ESTÁ AUTORIZADA EN EL SERVIDOR» con el
  identificador, el código y el contacto del administrador, y lo reintenta cada 30 s;
- la pantalla del televisor muestra el mismo mensaje y también lo reintenta.

En cuanto el administrador añade el dispositivo, el agente y después la pantalla se conectan
solos, sin reiniciar. El servidor guarda entonces el secreto del dispositivo.

> El código se calcula a partir del secreto: demuestra al administrador que la solicitud
> viene de esta Raspberry. Para volver a verlo: `python3 identity_manager.py --show`.

> Si se reinicia la identidad (`--reset`), la Raspberry obtiene un **nuevo identificador**
> que hay que volver a autorizar.

### 7. Ajustes que revisar en `config.py`

| Ajuste | Valor actual | Qué revisar |
|---|---|---|
| `LANGUAGE` | `fr` | Idioma de la Raspberry (`fr`, `en`, `es`) |
| `GREETING_NAME` | preguntado por `install.sh` | Cómo el anuncio llama a la persona («abuela», «papá», un nombre…); `None` = sin saludo |
| `WEATHER_CITY`, `WEATHER_POSTCODE`, `WEATHER_COUNTRY` | preguntados por `install.sh` | Lugar del tiempo de la pantalla de inicio de la TV: ciudad, código postal, país («España» o «ES»), cada uno puede valer `None`. Sin ciudad ni código postal: sin tiempo. Preguntados en la primera instalación (opciones `--city`, `--postcode`, `--country`), conservados por las actualizaciones; solo el lugar se envía al servicio del tiempo (Open-Meteo, a través del servidor). Reiniciar el agente tras un cambio |
| `SERVER_URL` | `wss://appelermami.fr` | Dirección de tu servidor |
| `MOUSE_DEVICE` | `None` (detección automática) | Solo hay que indicarlo para imponer un dispositivo concreto (varios ratones conectados): ruta estable de `ls -l /dev/input/by-id/` |
| `AUDIO_DEVICE` | `None` (detección automática) | Altavoz del tono: el primer altavoz USB encontrado. Solo hay que indicarlo para imponer una tarjeta concreta (nombre entre corchetes en `aplay -l`) |
| `CALL_AUDIO_OUTPUT` | `"auto"` | Salida del sonido de la llamada: el televisor (HDMI) si un televisor responde por HDMI-CEC y acepta sonido, si no el altavoz USB. `"hdmi"` o `"usb"` para imponerla |
| `SCREEN_MODE` | `"1080p"` | Resolución de la pantalla: un televisor que da 4K pasa a 1920 × 1080, hasta 60 Hz (llamadas más fluidas). `None` deja la pantalla como la quiere el televisor |
| `VOICE_REACTION` | `True` | Fuera de las llamadas, se mide el volumen del micrófono para que el robot de la página de la TV se mueva cuando alguien habla (no se graba ni se envía nada). `False` = micrófono nunca usado fuera de las llamadas |
| `VOICE_COMMANDS` | `True` | Órdenes de voz al robot («Robot hola», hora, tiempo, radio, volumen, llamada), reconocidas en la Raspberry (no se envía nada), nunca durante una llamada; necesita `VOICE_REACTION`. `False` = ninguna |
| `RADIO_STATIONS` | `None` (emisoras del país) | Radio: `None` = las emisoras del país de la tele (`radio_stations.py`: Francia, España, Reino Unido, Portugal, México, Estados Unidos; país de los ajustes, si no el idioma); o una lista propia: nombre, frecuencia FM (solo para pedirla) y dirección del flujo de cada emisora; se conserva al actualizar (la antigua lista de París del proyecto deja paso a las emisoras del país). El volumen dicho por voz se guarda en `radio_volume.txt` para la radio (0 a 100 %, 20 % al principio; barra de la página de la radio, página de ajustes, «Robot, volumen 5» mientras suena = 50 %) y en `voice_volume.txt` para la voz del robot (nivel 1 a 10, 8 al principio; página de ajustes, «Robot, volumen 5» con la radio apagada), la última emisora en `radio_station.txt` |
| `MOUSE_RETRY_DELAY` | `5` | Tiempo entre dos búsquedas del ratón cuando no está (segundos) |
| `HDMI_PORT` | `3` | Entrada HDMI del televisor, usada solo si el televisor no da la dirección de la Raspberry (normalmente se lee en el televisor: `cec-ctl -d /dev/cec0` muestra `Physical Address : 3.0.0.0` para la entrada 3) |
| `RINGTONE_PATH` | `~/AppelerMamie/ringtone.wav` | Otro tono: copia su `.mp3` en `~/AppelerMamie`, vuelve a lanzar `install.sh` (crea el `.wav`) e indica aquí la ruta del `.wav`. `install.sh` lo conserva; si falta el archivo, suena el tono del proyecto |
| `CALL_DURATION` | `30` | Tiempo de tono antes de abandonar (segundos) |
| `MAX_CACHED_CALLS` | `30` | Número de archivos de audio guardados en caché |
| `UNAUTHORIZED_RETRY_DELAY` | `30` | Tiempo entre dos intentos mientras el servidor rechaza el dispositivo |

El usuario que ejecuta el agente debe poder leer el ratón (grupo `input`).

### 8. Arranque

En funcionamiento normal, ambos programas arrancan automáticamente con la Raspberry:

- **el agente Python** se ejecuta como un servicio (ejecuta `start_tv_control.sh`);
- **Chromium** lo inicia `chromium-autolaunch.service`.

```bash
# Prueba manual del agente
./start_tv_control.sh

# Instalación del servicio Chromium (después de sustituir YOUR_USER)
sudo cp chromium-autolaunch.service /etc/systemd/system/
sudo systemctl enable --now chromium-autolaunch.service
```

> El servicio del agente Python es `ColdStart/tv-control.service` (sustituir `YOUR_USER`,
> lo que hace `install.sh`). Debe ejecutarse con el usuario de la Raspberry (no `root`); si
> no, `~/AppelerMamie` no apunta a la carpeta correcta.

## Actualizaciones a distancia

Una Raspberry instalada desde un **clon** del repositorio público (ver Instalación) puede
actualizarse desde el servidor, sin desplazarse:

```bash
node admin.js update rpi-xxxxxxxx v0.2.1      # en el servidor: una Raspberry
node admin.js update --all v0.2.1             # todas las Raspberry conectadas
```

- El servidor solo **indica** la versión que instalar: nunca envía código, archivos ni
  comandos. El agente escribe la versión en `~/AppelerMamie/update_request`.
- `update.sh` (root, `appelermamie-update.service`, lanzado por `appelermamie-update.path`)
  espera entonces el fin de una llamada, descarga las versiones (`git fetch`) y solo acepta
  una versión cuya etiqueta está **firmada** por la clave de `/etc/appelermamie/allowed_signers`
  (copiada una vez desde `ColdStart/allowed_signers` en la primera instalación) y **más
  reciente** que la instalada.
- Lanza `install.sh --update` (sin preguntas, la Raspberry no se reinicia) y espera a que el
  agente vuelva a conectarse; si no, **vuelve** a la versión anterior.
- Resultado: `node admin.js list` (versión de cada Raspberry), `node admin.js diagnose <id>`
  (versión instalada, última actualización), `journalctl -u appelermamie-update` en la Raspberry.

A mano, en la Raspberry: `cd ~/AppelerMamie-src && git fetch --tags && git checkout
v0.2.1 && bash install.sh --update`.

## Servidor de producción o de prueba

Durante el desarrollo, una copia del servidor funciona aparte (`wss://appelermami.fr:8443`)
para no tocar nunca el servidor que usa la familia. Un único ajuste elige el servidor:
`SERVER_URL` en `config.py`, usado por el agente **y** por la pantalla de la TV
(`launch_chromium.sh` lo lee). Para cambiar:

```bash
bash ~/AppelerMamie/switch_server.sh          # muestra el servidor actual
bash ~/AppelerMamie/switch_server.sh test     # servidor de prueba
bash ~/AppelerMamie/switch_server.sh prod     # servidor de producción
```

El agente y la pantalla de la TV se reinician solos. `install.sh` conserva este ajuste al
volver a ejecutarlo. En el servidor de prueba, la Raspberry ya no recibe las llamadas de la
aplicación normal (solo las de un APK de prueba o de `https://appelermami.fr:8443/appelant.html`).

## Pruebas automáticas

La carpeta [`tests/`](tests/) comprueba el agente, la reparación automática, el informe de
estado, el altavoz del timbre, el ratón, la entrada HDMI e `install.sh` (lanzado en una carpeta
personal falsa), **sin Raspberry**: archivos del sistema, comandos, TV y red están simulados.
Se ejecutan en un PC (Linux, o Windows con Git Bash) y `install.sh` no los copia en la Pi.

```bash
cd Raspberry_receiver   # la carpeta del proyecto (clon de CallTV-Raspberry)
pip install "websockets>=13,<18"
python3 tests/run_tests.py            # todas las pruebas
python3 tests/run_tests.py selfheal   # solo los archivos cuyo nombre contiene «selfheal»
```

GitHub también las lanza en cada envío (push).

## Solución de problemas

| Problema | Pista |
|---|---|
| «AÚN NO ESTÁ AUTORIZADA» | Envía el identificador al administrador del servidor (ver paso 6) |
| «EL SERVIDOR RECHAZA EL SECRETO» | `identity.json` ha cambiado: pide al administrador que retire y vuelva a autorizar el identificador |
| No suena el tono | Registros del agente: al arrancar, «Ringtone speaker: …» indica el altavoz encontrado; «No USB speaker found» significa que no se detecta ningún altavoz USB (el tono sale entonces por el televisor, que solo se oye si está encendido). Comprueba la conexión con `aplay -l` |
| El clic no responde la llamada | Registros del agente: busca «Mouse found» o «No mouse found». Comprueba los permisos de `/dev/input/` (grupo `input`) y, si hay varios ratones conectados, impón el correcto con `MOUSE_DEVICE` |
| El televisor no cambia de entrada, el mando no hace nada | `cec-ctl -d /dev/cec0` (dirección, «Playback» declarado) y `cec-ctl -d /dev/cec0 --to 0 --give-device-power-status`; comprobar que el CEC está activado en los ajustes del televisor (Anynet+, SimpLink, Bravia Sync…). No usar `cec-client`: al terminar, borra la configuración CEC (el agente vuelve a declarar la Raspberry en 30 s como máximo) |
| No hay anuncio de voz | gTTS necesita Internet; como alternativa solo se reproduce el tono |
| La pantalla del televisor no está en el idioma correcto | Comprueba `LANGUAGE` en `config.py` y reinicia el servicio Chromium |
| Un script `.sh` falla con `\r` | Finales de línea de Windows: `sed -i 's/\r$//' script.sh` |
