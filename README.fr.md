# CallTV — Récepteur Raspberry Pi

[English](README.md) | **Français** | [Español](README.es.md)

Le Raspberry Pi est branché sur la télévision de la personne appelée. Il fait tourner
**deux programmes** qui se connectent au serveur avec la même identité :

| Programme | Rôle |
|---|---|
| **Agent Python** (`main.py`) | Reçoit l'appel, joue l'annonce vocale, détecte le clic sur le bouton, allume la TV |
| **Chromium en mode kiosque** (`receveur.html`) | Affiche l'appel, active la caméra et le micro, établit la vidéo (WebRTC) |

> **Ce dépôt contient seulement le récepteur.** Les appels passent par un serveur et une
> application de téléphone qui ne sont pas publics : un Raspberry doit être autorisé sur le
> serveur avant de pouvoir recevoir des appels. **Pour utiliser l'ensemble, contactez-moi** en
> ouvrant une [issue](https://github.com/jgilles63/CallTV-Raspberry/issues).

## Matériel

- Raspberry Pi avec un environnement graphique (X11, écran `:0`) ;
- télévision compatible **HDMI-CEC**, avec le Raspberry branché sur une entrée HDMI (l'entrée est lue sur la TV elle-même ; `HDMI_PORT` de `config.py` seulement si la TV ne la donne pas) ;
- **webcam avec micro** (utilisée par Chromium) ;
- **souris USB** servant de bouton « décrocher » (dans une coque imprimée en 3D) ;
- **enceinte USB** pour la sonnerie (détectée automatiquement : n'importe quel modèle, n'importe
  quel port USB) ; le son de l'appel, lui, sort par la TV (HDMI) si c'est une TV qui répond en
  HDMI-CEC, sinon par l'enceinte USB (écran d'ordinateur sans son) ;
- connexion Internet (serveur + synthèse vocale Google).

Testé (15/10/2026, installation complète depuis une carte SD vierge) sur un **Raspberry Pi 4
Model B** avec **Raspberry Pi OS 64 bits avec bureau** (Debian 13 « trixie »), Chromium 154,
une webcam USB avec micro, une enceinte USB et une souris sans fil. Un écran sans HDMI-CEC
fonctionne aussi : il faut seulement l'allumer soi-même (l'état des lieux signale « TV vue par
HDMI-CEC : unknown »).

## Fichiers

| Fichier | Rôle |
|---|---|
| `main.py` | Point d'entrée : charge l'identité, met le volume à 100 %, lance l'agent |
| `agent.py` | Cœur de l'agent : WebSocket, appels entrants, clic souris, signal `SIGUSR1`, heartbeat |
| `config.py` | Tous les réglages (**langue**, URL du serveur, chemins, souris, durée d'appel, volumes) |
| `i18n.py` | Traductions (fr, en, es) : annonce vocale, messages de l'agent et des scripts d'installation |
| `identity.py` | Lit `identity.json` (identifiant + secret de l'appareil) |
| `tts_audio.py` | Génère l'annonce vocale, la mixe avec la sonnerie, la joue |
| `tv_control.py` | Pilote la TV en HDMI-CEC (`cec-ctl` du noyau Linux) : l'allume, change son entrée, demande son état ; garde le Raspberry déclaré à la TV comme lecteur |
| `remote_keys.py` | **Télécommande de la TV** par HDMI-CEC : le noyau transforme ses touches en clavier (`vc4-hdmi-0`), lu par l'agent : flèches, OK, Retour |
| `call_audio.py` | Choisit la sortie du son de l'appel : la TV (HDMI) ou l'enceinte USB |
| `display_mode.py` | **Résolution de l'écran** : une TV 4K est passée en 1920 × 1080 (jusqu'à 60 Hz), bien plus léger pour le Raspberry Pi 4 pendant un appel vidéo ; les écrans de 1920 pixels ou moins ne sont jamais changés (`wlr-randr`) |
| `start_tv_control.sh` | Lance l'agent dans son environnement virtuel Python |
| `ringtone.mp3` | Sonnerie : « game-music1 » de Nia Mi ([OpenGameArt](https://opengameart.org/node/153251)), domaine public (CC0) ; convertie en `.wav` et répétée pendant tout l'appel |
| `ColdStart/setup_identity.py` | **À lancer une fois** : crée l'identité de l'appareil et un QR code |
| `ColdStart/identity_manager.py` | Création, lecture et réinitialisation de l'identité |
| `ColdStart/launch_chromium.sh` | Ouvre `receveur.html` en plein écran avec l'identité et la langue de l'appareil |
| `ColdStart/chromium-autolaunch.service` | Service systemd qui lance Chromium au démarrage |
| `ColdStart/tv-control.service` | Service systemd de l'agent Python |
| `install.sh` | **Installation ou mise à jour en une commande** (voir Installation) |
| `selfheal.py` | Réparation automatique (Wi-Fi, page TV déconnectée ou bloquée pendant un appel, agent, redémarrage de nuit), en root chaque minute |
| `diagnostics.py`, `diagnose.sh` | État des lieux (demandé aussi par le serveur : `node admin.js diagnose`) |
| `update.sh` | **Mise à jour à distance** vers une version signée (voir « Mises à jour à distance ») |
| `ColdStart/allowed_signers` | Clé publique qui signe les versions (installée une fois sur le Raspberry) |
| `switch_server.sh` | Bascule le Raspberry entre le serveur de **production** et le serveur de **test** (voir plus bas) |
| `HomeAssistant/send_sigur_fromAlexa.sh` | Décroche à distance en envoyant `SIGUSR1` à l'agent |

## Langue

Un seul réglage pour tout le Raspberry : **`LANGUAGE` dans `config.py`** (`"fr"`, `"en"` ou
`"es"`). Il change :

- l'**annonce vocale** :

  | Langue | Annonce (avec `GREETING_NAME = "mamie"`) | Sans salutation (`None`) |
  |---|---|---|
  | `fr` | « Hé mamie, c'est *prénom* qui t'appelle » | « C'est *prénom* qui t'appelle » |
  | `en` | « Hey mamie, it's *prénom* calling » | « It's *prénom* calling » |
  | `es` | « Oye mamie, es *prénom* quien te llama » | « Es *prénom* quien te llama » |

  La salutation (`GREETING_NAME` : mamie, papi, maman, papa, un prénom…) est demandée par
  `install.sh` à la première installation (option `--greeting`) ;

- les messages de l'agent destinés à l'utilisateur et ceux de `setup_identity.py` (y compris
  le contenu de `setup_qr_code.txt`) ;
- l'**écran TV** : `launch_chromium.sh` lit `LANGUAGE` et l'ajoute à l'adresse de
  `receveur.html` (`&lang=…`) ;
- la langue des messages envoyés par le serveur à l'agent.

Après un changement, redémarrer l'agent **et** le service Chromium. Les annonces déjà en
cache ne sont pas réutilisées : le nom du fichier contient la langue. Les journaux techniques
de l'agent sont en anglais.

## Fonctionnement de l'agent

1. **Connexion** à `wss://appelermami.fr` et enregistrement (`register_device`), avec
   reconnexion automatique et un heartbeat toutes les 25 s.
2. **Appel entrant** (`incoming_call`) :
   - génère avec **gTTS** l'annonce dans la langue configurée ;
   - la mixe avec la sonnerie grâce à **ffmpeg**, sur 30 secondes ;
   - met le résultat en cache dans `cache_audio/` (un fichier par prénom et par langue,
     30 fichiers au maximum : les moins récemment utilisés sont supprimés) ;
   - le joue avec **aplay**. Si la synthèse échoue, la sonnerie seule est jouée.
3. **Décroché**, par l'un de ces trois moyens :
   - un **clic gauche** sur la souris (lue avec `evdev`, **détectée automatiquement** : n'importe
     quel modèle, n'importe quel port USB, retrouvée après un débranchement) ;
   - le signal **`SIGUSR1`** (`kill -USR1 <pid>`, voir `HomeAssistant/`) ;
   - le bouton **Répondre** de `receveur.html` (synchronisé par le serveur) ;
   - **OK sur la télécommande de la TV**, quand la TV affiche l'entrée du Raspberry (Retour
     refuse ; pendant l'appel, Retour raccroche).
4. **Allumage de la TV** (`tv_control.py`, `cec-ctl`) : `--image-view-on` pour allumer, puis
   `--active-source` (le Raspberry devient la source active, adresse donnée par la TV, par ex.
   `3.0.0.0` pour l'entrée 3) répété 5 fois, car certaines TV ne répondent pas du premier coup.
   Entre les deux, `--give-device-power-status` demande l'état de la TV : si une TV répond et accepte le son (ELD), le
   son de l'appel passe par la TV (`call_audio.py` rallume la sortie HDMI si PipeWire l'a coupée
   parce que la TV était en veille au démarrage du Pi) ; sinon il passe par l'enceinte USB. La
   sonnerie et l'annonce restent toujours sur l'enceinte USB.
5. **Sans réponse** au bout de 30 s, l'agent raccroche (`no_answer`).

La caméra n'est **pas** gérée par Python : c'est `receveur.html` qui l'active au moment du
décroché.
- **Appel depuis sa TV** : sur ordre du serveur (`outgoing_call_start`), l'agent allume la TV sur l'entrée du Raspberry, sans sonnerie, et la rend à la fin de l'appel. Pendant cet appel, la souris ne raccroche pas (on raccroche depuis le téléphone).

## Installation

### Installation automatique (recommandée)

1. **Carte SD** : avec [Raspberry Pi Imager](https://www.raspberrypi.com/software/), écrire
   **Raspberry Pi OS avec bureau** (64 bits). Dans les réglages d'Imager : nom d'utilisateur
   et mot de passe (au choix), Wi-Fi, **SSH activé**, et éventuellement un nom de machine.
2. **Télécharger le projet** sur le Raspberry (en SSH, avec l'utilisateur du Raspberry), en
   choisissant une version publiée (liste : « Releases » / « Tags » du dépôt) :
   ```bash
   git clone https://github.com/jgilles63/CallTV-Raspberry.git ~/AppelerMamie-src
   cd ~/AppelerMamie-src
   git checkout v0.2.6        # la dernière version (voir « Releases »)
   ```
   (`sudo apt install -y git` si git manque.) Ce dossier contient seulement le projet
   téléchargé : le script installe les programmes dans `~/AppelerMamie`.
3. **Lancer le script**, avec l'utilisateur du Raspberry (pas avec `sudo`) :
   ```bash
   bash install.sh            # demande la langue (fr / en / es)
   bash install.sh --lang es  # ou sans question
   ```
   À la première installation, il demande aussi comment l'annonce vocale appelle la
   personne (« Hé mamie, c'est Paul qui t'appelle », ou « papa », un prénom, ou rien).

Le script fait tout, rien d'autre à installer ni à copier :

- installe les **paquets système** (ffmpeg, v4l-utils pour `cec-ctl`, Chromium…) et l'**environnement
  Python** ;
- **copie les programmes** dans `~/AppelerMamie` et convertit la sonnerie ;
- règle la langue, les droits de l'utilisateur (souris, TV, son), crée l'**identité** de
  l'appareil ;
- installe et **démarre** les services (agent, Chromium sur la TV, réparation automatique),
  la connexion automatique au bureau, l'écran sans mise en veille, la caméra et le micro
  autorisés dans Chromium.

Il affiche à la fin **l'identifiant et le code de vérification** à faire autoriser par
l'administrateur du serveur (étape 6), puis propose de redémarrer.

**Mise à jour** vers une version plus récente : l'identité (`identity.json`) et les réglages
de `config.py` sont conservés (une copie de l'ancien `config.py` est gardée). Un journal est
écrit dans `~/appelermamie-install.log`.

```bash
cd ~/AppelerMamie-src
git fetch --tags
git checkout v0.2.0          # la nouvelle version
bash install.sh
```

### Installation manuelle (détail des étapes)

Tous les fichiers sont déployés **à plat** dans `~/AppelerMamie/`, c'est-à-dire le dossier
personnel de l'utilisateur du Raspberry (le contenu de `ColdStart/` compris). Les scripts
trouvent ce dossier automatiquement ; seul `chromium-autolaunch.service` doit être édité
(remplacer `YOUR_USER`).

### 1. Paquets système

```bash
sudo apt install ffmpeg alsa-utils v4l-utils cec-utils chromium python3-venv
```

### 2. Environnement Python

```bash
cd ~/AppelerMamie
python3 -m venv venv
source venv/bin/activate
pip install websockets evdev gTTS qrcode
```

### 3. Sonnerie au format WAV

`aplay` lit du WAV : convertir la sonnerie une fois (`install.sh` convertit tous les `.mp3`
du dossier). Elle dure quelques secondes : l'agent la répète pendant tout l'appel.

```bash
ffmpeg -i ringtone.mp3 ringtone.wav
```

### 4. Langue

Choisir la langue dans `config.py` **avant** l'étape suivante (les messages de
`setup_identity.py` l'utilisent) :

```python
LANGUAGE = "fr"   # "fr", "en" ou "es"
```

### 5. Identité de l'appareil

```bash
python3 setup_identity.py
```

Le script crée :

- `identity.json` (droits `600`) : identifiant `rpi-xxxxxxxx` et **secret** de l'appareil ;
- `setup_qr_code.txt` : QR code de l'identifiant, à scanner depuis l'application mobile.

> ⚠️ `identity.json` contient le secret de l'appareil : ne jamais le partager ni le committer.
> Pour afficher ou réinitialiser l'identité : `python3 identity_manager.py --show` / `--reset`.

### 6. Autorisation sur le serveur

Le serveur n'accepte que les Raspberry ajoutés par son administrateur. Envoyez-lui
**l'identifiant** (`rpi-xxxxxxxx`) **et le code de vérification** (`XXXX-XXXX-XXXX`),
affichés à la fin de l'installation et dans `setup_qr_code.txt` — jamais le secret —
par exemple en ouvrant une [issue sur le dépôt GitHub](https://github.com/jgilles63/CallTV-Raspberry/issues).

En attendant :

- l'agent affiche un message « CE RASPBERRY N'EST PAS ENCORE AUTORISÉ » avec l'identifiant,
  le code et le contact de l'administrateur, puis réessaie toutes les 30 s ;
- l'écran TV affiche le même message et réessaie lui aussi.

Dès que l'administrateur a ajouté l'appareil, l'agent puis l'écran se connectent tout seuls,
sans redémarrage. Le serveur retient alors le secret de l'appareil.

> Le code est calculé à partir du secret : il prouve à l'administrateur que la demande vient
> bien de ce Raspberry. Pour le revoir : `python3 identity_manager.py --show`.

> Si l'identité est réinitialisée (`--reset`), le Raspberry obtient un **nouvel identifiant**
> qu'il faut à nouveau faire autoriser.

### 7. Réglages à vérifier dans `config.py`

| Réglage | Valeur actuelle | À vérifier |
|---|---|---|
| `LANGUAGE` | `fr` | Langue du Raspberry (`fr`, `en`, `es`) |
| `GREETING_NAME` | demandé par `install.sh` | Comment l'annonce appelle la personne (« mamie », « papa », un prénom…) ; `None` = sans salutation |
| `SERVER_URL` | `wss://appelermami.fr` | Adresse de votre serveur |
| `MOUSE_DEVICE` | `None` (détection automatique) | À renseigner seulement pour imposer un appareil précis (plusieurs souris branchées) : chemin stable de `ls -l /dev/input/by-id/` |
| `AUDIO_DEVICE` | `None` (détection automatique) | Enceinte de la sonnerie : la première enceinte USB trouvée. À renseigner seulement pour imposer une carte précise (nom entre crochets dans `aplay -l`) |
| `CALL_AUDIO_OUTPUT` | `"auto"` | Sortie du son de l'appel : la TV (HDMI) si une TV répond en HDMI-CEC et accepte le son, sinon l'enceinte USB. `"hdmi"` ou `"usb"` pour l'imposer |
| `SCREEN_MODE` | `"1080p"` | Résolution de l'écran : une TV qui donne la 4K passe en 1920 × 1080, jusqu'à 60 Hz (appels plus fluides). `None` laisse l'écran comme la TV le veut |
| `MOUSE_RETRY_DELAY` | `5` | Délai entre deux recherches de la souris quand elle est absente (secondes) |
| `HDMI_PORT` | `3` | Entrée HDMI de la TV, utilisée seulement si la TV ne donne pas l'adresse du Raspberry (normalement lue sur la TV : `cec-ctl -d /dev/cec0` affiche `Physical Address : 3.0.0.0` pour l'entrée 3) |
| `RINGTONE_PATH` | `~/AppelerMamie/ringtone.wav` | Autre sonnerie : copier son `.mp3` dans `~/AppelerMamie`, relancer `install.sh` (il fait le `.wav`), puis indiquer ici le chemin du `.wav`. Conservé par `install.sh` ; si le fichier manque, la sonnerie du projet est jouée |
| `CALL_DURATION` | `30` | Durée de sonnerie avant abandon (secondes) |
| `MAX_CACHED_CALLS` | `30` | Nombre de fichiers audio gardés en cache |
| `UNAUTHORIZED_RETRY_DELAY` | `30` | Délai entre deux tentatives tant que le serveur refuse l'appareil |

L'utilisateur qui lance l'agent doit pouvoir lire la souris (groupe `input`).

### 8. Lancement

En fonctionnement normal, les deux programmes démarrent automatiquement avec le Raspberry :

- **l'agent Python** tourne comme un service (il exécute `start_tv_control.sh`) ;
- **Chromium** est lancé par `chromium-autolaunch.service`.

```bash
# Test manuel de l'agent
./start_tv_control.sh

# Installation du service Chromium (après avoir remplacé YOUR_USER)
sudo cp chromium-autolaunch.service /etc/systemd/system/
sudo systemctl enable --now chromium-autolaunch.service
```

> Le service de l'agent Python est `ColdStart/tv-control.service` (remplacer `YOUR_USER`,
> ce que fait `install.sh`). Il doit tourner sous l'utilisateur du Raspberry (et non
> `root`), sinon `~/AppelerMamie` ne pointe pas vers le bon dossier.

## Mises à jour à distance

Un Raspberry installé depuis un **clone** du dépôt public (voir Installation) peut être mis
à jour depuis le serveur, sans se déplacer :

```bash
node admin.js update rpi-xxxxxxxx v0.2.1      # sur le serveur : un Raspberry
node admin.js update --all v0.2.1             # tous les Raspberry en ligne
```

- Le serveur **indique** seulement la version à installer : il n'envoie jamais de code, de
  fichier ni de commande. L'agent écrit la version dans `~/AppelerMamie/update_request`.
- `update.sh` (root, `appelermamie-update.service`, lancé par `appelermamie-update.path`)
  attend alors la fin d'un appel, télécharge les versions (`git fetch`), et n'accepte qu'une
  version dont l'étiquette est **signée** par la clé de `/etc/appelermamie/allowed_signers`
  (copiée une fois depuis `ColdStart/allowed_signers` à la première installation) et **plus
  récente** que celle installée.
- Il lance `install.sh --update` (aucune question, le Raspberry n'est pas redémarré), puis
  attend que l'agent soit reconnecté ; sinon il **revient** à la version précédente.
- Résultat : `node admin.js list` (version de chaque Raspberry), `node admin.js diagnose <id>`
  (version installée, dernière mise à jour), `journalctl -u appelermamie-update` sur le Raspberry.

À la main, sur le Raspberry : `cd ~/AppelerMamie-src && git fetch --tags && git checkout
v0.2.1 && bash install.sh --update`.

## Serveur de production ou de test

Pendant le développement, une copie du serveur tourne à part (`wss://appelermami.fr:8443`)
pour ne jamais toucher au serveur utilisé par la famille. Un seul réglage choisit le
serveur : `SERVER_URL` dans `config.py`, utilisé par l'agent **et** par l'écran TV
(`launch_chromium.sh` le lit). Pour basculer :

```bash
bash ~/AppelerMamie/switch_server.sh          # affiche le serveur actuel
bash ~/AppelerMamie/switch_server.sh test     # serveur de test
bash ~/AppelerMamie/switch_server.sh prod     # serveur de production
```

L'agent et l'écran TV redémarrent tout seuls. `install.sh` conserve ce réglage quand on le
relance. Sur le serveur de test, le Raspberry ne reçoit plus les appels de l'application
normale (seulement ceux d'un APK de test ou de `https://appelermami.fr:8443/appelant.html`).

## Tests automatiques

Le dossier [`tests/`](tests/) vérifie l'agent, la réparation automatique, l'état des lieux,
l'enceinte de la sonnerie, la souris, l'entrée HDMI et `install.sh` (lancé dans un faux
dossier personnel), **sans Raspberry** : fichiers système, commandes, TV et réseau sont
simulés. Ils tournent sur un PC (Linux, ou Windows avec Git Bash) et ne sont pas copiés sur
le Pi par `install.sh`.

```bash
cd Raspberry_receiver   # le dossier du projet (clone de CallTV-Raspberry)
pip install "websockets>=13,<18"
python3 tests/run_tests.py            # tous les tests
python3 tests/run_tests.py selfheal   # seulement les fichiers dont le nom contient « selfheal »
```

GitHub les lance aussi à chaque envoi (push).

## Dépannage

| Problème | Piste |
|---|---|
| « N'EST PAS ENCORE AUTORISÉ » | Envoyer l'identifiant à l'administrateur du serveur (voir étape 6) |
| « LE SERVEUR REFUSE LE SECRET » | `identity.json` a changé : demander à l'administrateur de retirer puis ré-autoriser l'identifiant |
| Pas de sonnerie | Journaux de l'agent : au démarrage, « Ringtone speaker: … » indique l'enceinte trouvée ; « No USB speaker found » signifie qu'aucune enceinte USB n'est détectée (la sonnerie passe alors par la TV, entendue seulement si elle est allumée). Vérifier le branchement avec `aplay -l` |
| Le clic ne décroche pas | Journaux de l'agent : chercher « Mouse found » ou « No mouse found ». Vérifier les droits sur `/dev/input/` (groupe `input`) et, si plusieurs souris sont branchées, imposer la bonne avec `MOUSE_DEVICE` |
| La TV ne bascule pas, la télécommande ne fait rien | `cec-ctl -d /dev/cec0` (adresse, « Playback » déclaré) et `cec-ctl -d /dev/cec0 --to 0 --give-device-power-status` ; vérifier que le CEC est activé dans les réglages de la TV (Anynet+, SimpLink, Bravia Sync…). Ne pas utiliser `cec-client` : en se terminant, il efface la configuration CEC (l'agent redéclare le Raspberry en 30 s au plus) |
| Annonce vocale absente | gTTS a besoin d'Internet ; la sonnerie seule est jouée en secours |
| L'écran TV n'est pas dans la bonne langue | Vérifier `LANGUAGE` dans `config.py`, puis redémarrer le service Chromium |
| Script `.sh` qui échoue avec `\r` | Fin de ligne Windows : `sed -i 's/\r$//' script.sh` |
