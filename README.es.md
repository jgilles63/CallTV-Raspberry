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
- televisor compatible con **HDMI-CEC**, con la Raspberry conectada a una entrada HDMI (**HDMI 3** por defecto, ajuste `HDMI_PORT` de `config.py`);
- **webcam con micrófono** (usada por Chromium);
- **ratón USB** que sirve de botón para «responder» (dentro de una carcasa impresa en 3D);
- **altavoz USB** para el tono de llamada (detectado automáticamente: cualquier modelo, cualquier
  puerto USB); el sonido de la llamada sale por el televisor (HDMI);
- conexión a Internet (servidor + síntesis de voz de Google).

## Archivos

| Archivo | Función |
|---|---|
| `main.py` | Punto de entrada: carga la identidad, pone el volumen al 100 %, inicia el agente |
| `agent.py` | Núcleo del agente: WebSocket, llamadas entrantes, clic del ratón, señal `SIGUSR1`, heartbeat |
| `config.py` | Todos los ajustes (**idioma**, URL del servidor, rutas, ratón, duración de llamada, volúmenes) |
| `i18n.py` | Traducciones (fr, en, es): anuncio de voz, mensajes del agente y de los scripts de instalación |
| `identity.py` | Lee `identity.json` (identificador + secreto del dispositivo) |
| `tts_audio.py` | Genera el anuncio de voz, lo mezcla con el tono y lo reproduce |
| `tv_control.py` | Controla el televisor mediante HDMI-CEC (`cec-client`) |
| `start_tv_control.sh` | Inicia el agente en su entorno virtual de Python |
| `ringtone.mp3` | Tono: «game-music1» de Nia Mi ([OpenGameArt](https://opengameart.org/node/153251)), dominio público (CC0); convertido a `.wav` y repetido durante toda la llamada |
| `ColdStart/setup_identity.py` | **Ejecutar una vez**: crea la identidad del dispositivo y un código QR |
| `ColdStart/identity_manager.py` | Crea, lee y reinicia la identidad |
| `ColdStart/launch_chromium.sh` | Abre `receveur.html` a pantalla completa con la identidad y el idioma del dispositivo |
| `ColdStart/chromium-autolaunch.service` | Servicio systemd que inicia Chromium al arrancar |
| `ColdStart/tv-control.service` | Servicio systemd del agente Python |
| `install.sh` | **Instalación o actualización con un solo comando** (ver Instalación) |
| `switch_server.sh` | Cambia la Raspberry entre el servidor de **producción** y el servidor de **prueba** (ver más abajo) |
| `HomeAssistant/send_sigur_fromAlexa.sh` | Responde a distancia enviando `SIGUSR1` al agente |

## Idioma

Un solo ajuste para toda la Raspberry: **`LANGUAGE` en `config.py`** (`"fr"`, `"en"` o
`"es"`). Cambia:

- el **anuncio de voz**:

  | Idioma | Anuncio |
  |---|---|
  | `fr` | «Hé mamie, c'est *nombre* qui t'appelle» |
  | `en` | «Hey grandma, it's *nombre* calling» |
  | `es` | «Oye abuela, es *nombre* quien te llama» |

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
   - el botón **Responder** de `receveur.html` (sincronizado por el servidor).
4. **Encendido del televisor** (`tv_control.py`): `on 0` para encenderlo y después `as` (la
   Raspberry pasa a ser la fuente activa, puerto 3) repetido 5 veces, porque algunos
   televisores no responden al primer intento.
5. **Sin respuesta** después de 30 s, el agente cuelga (`no_answer`).

La cámara **no** la gestiona Python: la activa `receveur.html` en el momento de responder.
- **Llamada desde su TV**: por orden del servidor (`outgoing_call_start`), el agente enciende la TV en la entrada de la Raspberry, sin timbre, y la devuelve al final de la llamada. Durante esta llamada, el ratón no cuelga (se cuelga desde el teléfono).

## Instalación

### Instalación automática (recomendada)

1. **Tarjeta SD**: con [Raspberry Pi Imager](https://www.raspberrypi.com/software/), escribir
   **Raspberry Pi OS con escritorio** (64 bits). En los ajustes de Imager: nombre de usuario y
   contraseña (a elegir), Wi-Fi, **SSH activado** y, si se quiere, un nombre de equipo.
2. **Copiar esta carpeta** `Raspberry_receiver` en la Raspberry, desde un PC:
   ```bash
   scp -r Raspberry_receiver USUARIO@IP_DE_LA_PI:~/
   ```
3. **Ejecutar el script** por SSH, con el usuario de la Raspberry (no con `sudo`):
   ```bash
   cd ~/Raspberry_receiver
   bash install.sh            # pregunta el idioma (fr / en / es)
   bash install.sh --lang es  # o sin pregunta
   ```

El script hace todo lo que detallan los pasos 1 a 8 siguientes: paquetes del sistema, entorno
Python, conversión del tono, idioma, permisos del usuario (ratón, TV, sonido), identidad del
dispositivo, servicios de arranque automático (agente y Chromium), inicio de sesión automático
en el escritorio, pantalla sin reposo, cámara y micrófono permitidos en Chromium. Al final
muestra **el identificador y el código QR** que el administrador del servidor debe autorizar
(paso 6) y propone reiniciar.

Se puede **volver a ejecutar en cualquier momento para actualizar** la Raspberry: la identidad
(`identity.json`) y los ajustes de `config.py` se conservan (se guarda una copia del
`config.py` anterior). Se escribe un registro en `~/appelermamie-install.log`.

### Instalación manual (paso a paso)

Todos los archivos se despliegan **en una misma carpeta**, `~/AppelerMamie/`, es decir, la
carpeta personal del usuario de la Raspberry (incluido el contenido de `ColdStart/`). Los
scripts encuentran esta carpeta automáticamente; solo hay que editar
`chromium-autolaunch.service` (sustituir `YOUR_USER`).

### 1. Paquetes del sistema

```bash
sudo apt install ffmpeg alsa-utils cec-utils chromium python3-venv
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
| `SERVER_URL` | `wss://appelermami.fr` | Dirección de tu servidor |
| `MOUSE_DEVICE` | `None` (detección automática) | Solo hay que indicarlo para imponer un dispositivo concreto (varios ratones conectados): ruta estable de `ls -l /dev/input/by-id/` |
| `AUDIO_DEVICE` | `None` (detección automática) | Altavoz del tono: el primer altavoz USB encontrado. Solo hay que indicarlo para imponer una tarjeta concreta (nombre entre corchetes en `aplay -l`) |
| `MOUSE_RETRY_DELAY` | `5` | Tiempo entre dos búsquedas del ratón cuando no está (segundos) |
| `HDMI_PORT` | `3` | Entrada HDMI del televisor donde está conectada la Raspberry (el televisor cambia a ella al descolgar). Comprobación: `echo "scan" \| cec-client -s -d 1` muestra la Raspberry en la dirección `3.0.0.0` para la entrada 3 |
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
cd Raspberry_receiver
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
| El televisor no cambia de entrada | `echo "scan" \| cec-client -s -d 1` para comprobar el CEC |
| No hay anuncio de voz | gTTS necesita Internet; como alternativa solo se reproduce el tono |
| La pantalla del televisor no está en el idioma correcto | Comprueba `LANGUAGE` en `config.py` y reinicia el servicio Chromium |
| Un script `.sh` falla con `\r` | Finales de línea de Windows: `sed -i 's/\r$//' script.sh` |
