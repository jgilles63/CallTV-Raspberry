# ============================================
# FILE: i18n.py
# ============================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Translations of the texts of the Raspberry (voice announcement, agent
messages, setup scripts).

The language is chosen with LANGUAGE in config.py ("fr", "en" or "es").
Placeholders such as {name} are replaced by the matching parameter.
"""

import config

SUPPORTED_LANGUAGES = ("fr", "en", "es")

MESSAGES = {
    "fr": {
        # --- Voice announcement ---
        "tts.phrase": "Hé {greeting}, c'est {name} qui t'appelle",
        "tts.phraseNoGreeting": "C'est {name} qui t'appelle",
        "tts.someone": "quelqu'un",

        # --- Agent: refusal by the server ---
        "agent.notAuthorized": """
╔══════════════════════════════════════════════════════════════╗
║  ⛔ CE RASPBERRY N'EST PAS ENCORE AUTORISÉ SUR LE SERVEUR      ║
╚══════════════════════════════════════════════════════════════╝
  Identifiant : {device_id}
  Code        : {code}
  Serveur     : {server}

  Pour l'utiliser, demandez à l'administrateur du serveur de
  l'ajouter, en lui envoyant cet identifiant ET ce code de
  vérification (node admin.js add {device_id} {code}).
  Par exemple via :
    {contact}

  L'agent réessaie toutes les {delay} s et se connectera
  automatiquement dès que l'appareil sera autorisé.
""",
        "agent.secretRefused": """
╔══════════════════════════════════════════════════════════════╗
║  ⛔ LE SERVEUR REFUSE LE SECRET DE CE RASPBERRY               ║
╚══════════════════════════════════════════════════════════════╝
  Identifiant : {device_id}
  Le secret de identity.json ne correspond pas à celui que le
  serveur a enregistré pour cet appareil (identité réinitialisée ?).
  Demandez à l'administrateur du serveur de retirer puis de
  ré-autoriser cet identifiant.
  Message du serveur : {message}
""",
        "agent.adminFallback": "l'administrateur du serveur",
        "agent.stillRefused": "⛔ Toujours refusé par le serveur ({code})",
        "agent.nowAuthorized": "✅ Appareil autorisé par le serveur : connexion établie",
        "agent.retryUnauthorized": "⏳ Nouvelle tentative dans {delay} s (en attente d'autorisation du serveur)...",

        # --- Health report (diagnostics.py) ---
        "diag.title": "🩺 État des lieux du Raspberry {device_id} ({time})",
        "diag.logs": "Dernières erreurs de {service} :",
        "diag.noErrors": "(aucune)",
        "diag.check.system.model": "Modèle",
        "diag.check.system.os": "Système",
        "diag.check.system.uptime": "Allumé depuis (jours h:min)",
        "diag.check.service.tvControl": "Service de l'agent (tv-control)",
        "diag.check.service.chromium": "Service de l'écran (chromium-autolaunch)",
        "diag.check.version.chromium": "Version de Chromium",
        "diag.check.network.server": "Serveur joignable",
        "diag.check.network.interfaces": "Réseau actif",
        "diag.check.network.wifi": "Signal Wi-Fi",
        "diag.check.system.watchdog": "Chien de garde matériel",
        "diag.check.selfheal": "Réparation automatique (état, dernière action, nombre)",
        "diag.check.version": "Version installée",
        "diag.check.update": "Mises à jour à distance (état, dernière)",
        "diag.check.network.powersave": "Économie d'énergie du Wi-Fi",
        "diag.check.hdmi": "Câble HDMI",
        "diag.check.cec": "TV vue par HDMI-CEC",
        "diag.check.camera": "Caméra",
        "diag.check.microphone": "Micro",
        "diag.check.speaker": "Haut-parleur de la sonnerie",
        "diag.check.mouse": "Souris (bouton pour décrocher)",
        "diag.check.disk": "Disque (libre / total)",
        "diag.check.memory": "Mémoire (disponible / total)",
        "diag.check.temperature": "Température",
        "diag.check.power": "Alimentation",
        "diag.power.now": "{flag} (maintenant)",
        "diag.power.boot": "{flag} (depuis le démarrage)",
        "diag.flag.underVoltage": "tension trop faible",
        "diag.flag.freqCapped": "fréquence limitée",
        "diag.flag.throttled": "ralenti",
        "diag.flag.softTempLimit": "limite de température",

        # --- Identity loading (identity.py) ---
        "identity.fileNotFound": "❌ Fichier {path} introuvable !",
        "identity.runSetupFirst": "   Lancez d'abord : python3 setup_identity.py",
        "identity.invalid": "❌ identity.json invalide !",
        "identity.jsonError": "❌ Erreur de lecture du JSON : {error}",
        "identity.error": "❌ Erreur : {error}",
        "identity.loaded": "✅ Identité chargée depuis {path}",
        "identity.deviceId": "   Identifiant : {device_id}",

        # --- Identity manager (identity_manager.py) ---
        "manager.loading": "📂 Chargement de l'identité depuis {path}",
        "manager.loaded": "✅ Identité chargée : {device_id}",
        "manager.notFoundGenerating": "🆕 Aucune identité trouvée, génération...",
        "manager.created": "✅ Identité créée : {device_id}",
        "manager.saved": "💾 Identité sauvegardée (écriture atomique) : {path}",
        "manager.permissions": "   Permissions : 0o600 (propriétaire du fichier uniquement)",
        "manager.saveError": "❌ Erreur lors de la sauvegarde : {error}",
        "manager.corrupted": "❌ Fichier identity.json corrompu : {error}",
        "manager.fileNotFound": "❌ Fichier introuvable : {path}",
        "manager.title": "📱 IDENTITÉ DU RASPBERRY",
        "manager.idLabel": "  raspberryId  : {value}",
        "manager.createdLabel": "  createdAt    : {value}",
        "manager.secretLabel": "  deviceSecret : {value}",
        "manager.secretMasked": "  deviceSecret : {value} (masqué)",
        "manager.codeLabel": "  code         : {value} (code de vérification, à donner à l'administrateur)",
        "manager.backup": "💾 Sauvegarde de l'ancienne identité : {path}",
        "manager.generatingNew": "🔄 Génération d'une nouvelle identité...",
        "manager.newIdentity": "✅ Nouvelle identité : {device_id}",
        "manager.confirmReset": "⚠️  Voulez-vous vraiment réinitialiser l'identité ? (o/n) : ",
        "manager.cancelled": "❌ Annulé",
        "manager.unknownCommand": "❌ Commande inconnue : {command}",
        "manager.usage": """Utilisation :
  python3 identity_manager.py --show          (affiche l'ID, masque le secret)
  python3 identity_manager.py --show-secret   (affiche l'ID ET le secret)
  python3 identity_manager.py --reset         (nouvelle identité, sauvegarde .bak)""",

        # --- First setup (setup_identity.py) ---
        "setup.title": "🚀 INITIALISATION DE L'IDENTITÉ DU RASPBERRY PI",
        "setup.exists": "✅ Une identité existe déjà.\n",
        "setup.askReset": "Voulez-vous la réinitialiser ? (o/n) : ",
        "setup.resetDone": "\n✅ Réinitialisation terminée",
        "setup.backupKept": "   (ancienne identité sauvegardée en .bak)\n",
        "setup.cancelled": "❌ Annulé, identité conservée\n",
        "setup.generatingFirst": "🆕 Génération de la première identité...\n",
        "setup.done": "\n✅ Initialisation terminée !",
        "setup.file": "   Fichier : {path}",
        "setup.permissions": "   Permissions : 0o600 (propriétaire du fichier uniquement)",
        "setup.permanent": "   Cette identité est PERMANENTE\n",
        "setup.nextSteps": """ℹ️  Prochaines étapes :
   1. 📨 Envoyer l'ID et le code de vérification à l'administrateur
      du serveur pour qu'il autorise ce Raspberry — jamais le secret
   2. 📡 Démarrer l'agent : il se connecte dès que l'ID est autorisé
   3. 📱 Scanner le QR code dans l'application pour ajouter le contact""",
        "setup.qrSaved": "✅ QR code sauvegardé : {path}",
        "setup.qrFile": """
╔════════════════════════════════════════════════════════════════╗
║                    APPELER MAMIE - INSTALLATION               ║
╚════════════════════════════════════════════════════════════════╝

📱 IDENTIFIANT DU RASPBERRY (À SCANNER)
{qr}
📝 Identifiant (à recopier à la main) : {device_id}
🔑 Code de vérification : {code}
   (à donner à l'administrateur avec l'identifiant ; ce n'est pas le secret)

Le code secret est stocké séparément dans identity.json.
Ne le transmettez à personne : il ne quitte jamais ce Raspberry.

╔════════════════════════════════════════════════════════════════╗
║                    PROCHAINES ÉTAPES                          ║
╚════════════════════════════════════════════════════════════════╝

1. 📨 Envoyer l'ID et le code de vérification à l'administrateur du
   serveur pour qu'il autorise ce Raspberry
   (node admin.js add {device_id} {code})
2. 📡 Démarrer l'agent : il se connecte dès que l'ID est autorisé
3. 📱 Scanner ce QR code dans l'application pour ajouter le contact
""",

        # --- install.sh ---
        "install.title": "🚀 INSTALLATION D'APPELER MAMIE SUR CE RASPBERRY",
        "install.noRoot": "❌ Ne lancez pas ce script avec sudo : lancez-le avec l'utilisateur du Raspberry (le mot de passe sera demandé quand il le faut).",
        "install.sudo": "🔑 Le mot de passe de l'utilisateur va être demandé (droits administrateur).",
        "install.checks": "Vérifications",
        "install.noInternet": "❌ Pas de connexion internet : vérifiez le Wi-Fi puis relancez le script.",
        "install.noDesktop": "⚠️ Aucun bureau graphique détecté : Chromium ne pourra pas s'afficher sur la TV. Il faut Raspberry Pi OS avec bureau.",
        "install.askContinue": "Continuer quand même ? (o/n) : ",
        "install.stopped": "❌ Installation arrêtée.",
        "install.packages": "Paquets système (quelques minutes)",
        "install.files": "Fichiers du projet dans {dir}",
        "install.configKept": "   Réglages existants conservés (ancien fichier : {backup})",
        "install.mouseReset": "   MOUSE_DEVICE = {old} (chemin instable) remplacé par la détection automatique",
        "install.python": "Environnement Python",
        "install.ringtone": "Sonnerie",
        "install.groups": "Droits de l'utilisateur (souris, TV, son)",
        "install.identity": "Identité du Raspberry",
        "install.identityKept": "   Identité existante conservée : {device_id}",
        "install.services": "Démarrage automatique (agent et écran)",
        "install.selfheal": "Réparation automatique (Wi-Fi, écran, agent, redémarrage de nuit)",
        "install.updates": "Mises à jour à distance (versions signées seulement)",
        "install.updatesNoClone": "ℹ️ Dossier du projet copié (pas cloné avec git) : mises à jour à distance impossibles, seulement à la main.",
        "install.packagesUnchanged": "✅ Paquets inchangés depuis la dernière installation",
        "install.updated": "✅ Version {version} installée, programmes redémarrés.",
        "install.display": "Écran : session automatique, pas de mise en veille, caméra et micro autorisés",
        "install.displayManual": "⚠️ raspi-config indisponible : activez à la main la connexion automatique au bureau et désactivez la mise en veille de l'écran.",
        "install.failed": "❌ Échec pendant l'étape « {step} ». Détails dans {log}",
        "install.done": """
╔══════════════════════════════════════════════════════════════╗
║  ✅ INSTALLATION TERMINÉE                                     ║
╚══════════════════════════════════════════════════════════════╝
  Identifiant du Raspberry : {device_id}
  Code de vérification     : {code}

  Il reste à :
  1. Faire autoriser cet identifiant et ce code par l'administrateur
     du serveur (sur le serveur : node admin.js add {device_id} {code})
  2. Scanner le QR code ci-dessus dans l'application
  3. Redémarrer le Raspberry (les droits et l'écran ne sont
     appliqués qu'après un redémarrage)
""",
        "install.askReboot": "Redémarrer maintenant ? (o/n) : ",
        "install.askGreeting": "\n🔊 L'annonce d'un appel dira par exemple « Hé mamie, c'est Paul qui t'appelle ».\n   Comment appeler la personne ? (mamie, papi, maman, papa, son prénom...)\n   Entrée = sans : « C'est Paul qui t'appelle » : ",
        "install.greeting": "🔊 Annonce d'un appel : « {phrase} » (GREETING_NAME dans config.py pour la changer)",
        "install.greetingKept": "🔊 Annonce d'un appel inchangée : « {phrase} » (GREETING_NAME ajouté dans config.py)",
        "install.rebooting": "🔄 Redémarrage...",
        "install.restarted": "✅ Services redémarrés. Pensez à redémarrer plus tard (sudo reboot).",
        "switch.noRoot": "❌ Ne lancez pas ce script avec sudo : lancez-le avec l'utilisateur du Raspberry.",
        "switch.usage": "Usage : bash switch_server.sh [test | prod]   (sans argument : affiche le serveur actuel)",
        "switch.current": "🌐 Serveur actuel : {server}",
        "switch.prodName": "PRODUCTION (wss://appelermami.fr)",
        "switch.testName": "TEST (wss://appelermami.fr:8443, copie du serveur pour le développement)",
        "switch.otherName": "autre ({url})",
        "switch.noSetting": "❌ Réglage SERVER_URL introuvable dans {file}.",
        "switch.already": "ℹ️ Ce Raspberry est déjà sur le serveur {server} : rien à changer.",
        "switch.done": "✅ Ce Raspberry est maintenant sur le serveur {server}.",
        "switch.restarting": "🔄 Redémarrage de l'agent et de la page TV (mot de passe demandé)...",
        "switch.restarted": "✅ C'est fait. La TV se reconnecte dans une vingtaine de secondes.\n   Vérification : sudo journalctl -u tv-control -n 15 --no-pager",
    },

    "en": {
        # --- Voice announcement ---
        "tts.phrase": "Hey {greeting}, it's {name} calling",
        "tts.phraseNoGreeting": "It's {name} calling",
        "tts.someone": "someone",

        # --- Agent: refusal by the server ---
        "agent.notAuthorized": """
╔══════════════════════════════════════════════════════════════╗
║  ⛔ THIS RASPBERRY IS NOT AUTHORIZED ON THE SERVER YET         ║
╚══════════════════════════════════════════════════════════════╝
  Identifier : {device_id}
  Code       : {code}
  Server     : {server}

  To use it, ask the server administrator to add it by sending
  them this identifier AND this verification code
  (node admin.js add {device_id} {code}). For example via:
    {contact}

  The agent retries every {delay} s and will connect
  automatically as soon as the device is authorized.
""",
        "agent.secretRefused": """
╔══════════════════════════════════════════════════════════════╗
║  ⛔ THE SERVER REFUSES THE SECRET OF THIS RASPBERRY            ║
╚══════════════════════════════════════════════════════════════╝
  Identifier : {device_id}
  The secret in identity.json does not match the one the server
  recorded for this device (identity reset?).
  Ask the server administrator to remove and then authorize
  this identifier again.
  Server message: {message}
""",
        "agent.adminFallback": "the server administrator",
        "agent.stillRefused": "⛔ Still refused by the server ({code})",
        "agent.nowAuthorized": "✅ Device authorized by the server: connected",
        "agent.retryUnauthorized": "⏳ Retrying in {delay} s (waiting for the server's authorization)...",

        # --- Health report (diagnostics.py) ---
        "diag.title": "🩺 Health report of Raspberry {device_id} ({time})",
        "diag.logs": "Last errors of {service}:",
        "diag.noErrors": "(none)",
        "diag.check.system.model": "Model",
        "diag.check.system.os": "System",
        "diag.check.system.uptime": "Up for (days h:min)",
        "diag.check.service.tvControl": "Agent service (tv-control)",
        "diag.check.service.chromium": "Screen service (chromium-autolaunch)",
        "diag.check.version.chromium": "Chromium version",
        "diag.check.network.server": "Server reachable",
        "diag.check.network.interfaces": "Active network",
        "diag.check.network.wifi": "Wi-Fi signal",
        "diag.check.system.watchdog": "Hardware watchdog",
        "diag.check.selfheal": "Self-repair (state, last action, count)",
        "diag.check.version": "Installed version",
        "diag.check.update": "Remote updates (state, last one)",
        "diag.check.network.powersave": "Wi-Fi power saving",
        "diag.check.hdmi": "HDMI cable",
        "diag.check.cec": "TV seen through HDMI-CEC",
        "diag.check.camera": "Camera",
        "diag.check.microphone": "Microphone",
        "diag.check.speaker": "Ringtone speaker",
        "diag.check.mouse": "Mouse (answer button)",
        "diag.check.disk": "Disk (free / total)",
        "diag.check.memory": "Memory (available / total)",
        "diag.check.temperature": "Temperature",
        "diag.check.power": "Power supply",
        "diag.power.now": "{flag} (now)",
        "diag.power.boot": "{flag} (since startup)",
        "diag.flag.underVoltage": "under-voltage",
        "diag.flag.freqCapped": "frequency capped",
        "diag.flag.throttled": "throttled",
        "diag.flag.softTempLimit": "temperature limit",

        # --- Identity loading (identity.py) ---
        "identity.fileNotFound": "❌ File {path} not found!",
        "identity.runSetupFirst": "   First run: python3 setup_identity.py",
        "identity.invalid": "❌ Invalid identity.json!",
        "identity.jsonError": "❌ JSON read error: {error}",
        "identity.error": "❌ Error: {error}",
        "identity.loaded": "✅ Identity loaded from {path}",
        "identity.deviceId": "   Identifier: {device_id}",

        # --- Identity manager (identity_manager.py) ---
        "manager.loading": "📂 Loading the identity from {path}",
        "manager.loaded": "✅ Identity loaded: {device_id}",
        "manager.notFoundGenerating": "🆕 No identity found, generating...",
        "manager.created": "✅ Identity created: {device_id}",
        "manager.saved": "💾 Identity saved (atomic write): {path}",
        "manager.permissions": "   Permissions: 0o600 (file owner only)",
        "manager.saveError": "❌ Error while saving: {error}",
        "manager.corrupted": "❌ Corrupted identity.json file: {error}",
        "manager.fileNotFound": "❌ File not found: {path}",
        "manager.title": "📱 RASPBERRY IDENTITY",
        "manager.idLabel": "  raspberryId  : {value}",
        "manager.createdLabel": "  createdAt    : {value}",
        "manager.secretLabel": "  deviceSecret : {value}",
        "manager.secretMasked": "  deviceSecret : {value} (masked)",
        "manager.codeLabel": "  code         : {value} (verification code, to give to the administrator)",
        "manager.backup": "💾 Backing up the old identity: {path}",
        "manager.generatingNew": "🔄 Generating a new identity...",
        "manager.newIdentity": "✅ New identity: {device_id}",
        "manager.confirmReset": "⚠️  Do you really want to reset the identity? (y/n): ",
        "manager.cancelled": "❌ Cancelled",
        "manager.unknownCommand": "❌ Unknown command: {command}",
        "manager.usage": """Usage:
  python3 identity_manager.py --show          (shows the ID, hides the secret)
  python3 identity_manager.py --show-secret   (shows the ID AND the secret)
  python3 identity_manager.py --reset         (new identity, .bak backup)""",

        # --- First setup (setup_identity.py) ---
        "setup.title": "🚀 RASPBERRY PI IDENTITY SETUP",
        "setup.exists": "✅ An identity already exists.\n",
        "setup.askReset": "Do you want to reset it? (y/n): ",
        "setup.resetDone": "\n✅ Reset complete",
        "setup.backupKept": "   (old identity backed up as .bak)\n",
        "setup.cancelled": "❌ Cancelled, identity kept\n",
        "setup.generatingFirst": "🆕 Generating the first identity...\n",
        "setup.done": "\n✅ Setup complete!",
        "setup.file": "   File: {path}",
        "setup.permissions": "   Permissions: 0o600 (file owner only)",
        "setup.permanent": "   This identity is PERMANENT\n",
        "setup.nextSteps": """ℹ️  Next steps:
   1. 📨 Send the ID and the verification code to the server
      administrator so they authorize this Raspberry — never the secret
   2. 📡 Start the agent: it connects as soon as the ID is authorized
   3. 📱 Scan the QR code in the app to add the contact""",
        "setup.qrSaved": "✅ QR code saved: {path}",
        "setup.qrFile": """
╔════════════════════════════════════════════════════════════════╗
║                    CALL GRANDMA - SETUP                       ║
╚════════════════════════════════════════════════════════════════╝

📱 RASPBERRY IDENTIFIER (TO SCAN)
{qr}
📝 Identifier (to copy by hand): {device_id}
🔑 Verification code: {code}
   (to give to the administrator with the identifier; it is not the secret)

The secret code is stored separately in identity.json.
Never share it: it never leaves this Raspberry.

╔════════════════════════════════════════════════════════════════╗
║                    NEXT STEPS                                 ║
╚════════════════════════════════════════════════════════════════╝

1. 📨 Send the ID and the verification code to the server
   administrator so they authorize this Raspberry
   (node admin.js add {device_id} {code})
2. 📡 Start the agent: it connects as soon as the ID is authorized
3. 📱 Scan this QR code in the app to add the contact
""",

        # --- install.sh ---
        "install.title": "🚀 INSTALLING CALL GRANDMA ON THIS RASPBERRY",
        "install.noRoot": "❌ Do not run this script with sudo: run it as the Raspberry user (the password is asked when needed).",
        "install.sudo": "🔑 The user password will be asked (administrator rights).",
        "install.checks": "Checks",
        "install.noInternet": "❌ No internet connection: check the Wi-Fi, then run the script again.",
        "install.noDesktop": "⚠️ No desktop found: Chromium will not be able to show on the TV. Raspberry Pi OS with desktop is required.",
        "install.askContinue": "Continue anyway? (y/n): ",
        "install.stopped": "❌ Installation stopped.",
        "install.packages": "System packages (a few minutes)",
        "install.files": "Project files in {dir}",
        "install.configKept": "   Existing settings kept (old file: {backup})",
        "install.mouseReset": "   MOUSE_DEVICE = {old} (unstable path) replaced by automatic detection",
        "install.python": "Python environment",
        "install.ringtone": "Ringtone",
        "install.groups": "User rights (mouse, TV, sound)",
        "install.identity": "Raspberry identity",
        "install.identityKept": "   Existing identity kept: {device_id}",
        "install.services": "Automatic start (agent and screen)",
        "install.selfheal": "Self-repair (Wi-Fi, screen, agent, nightly restart)",
        "install.updates": "Remote updates (signed versions only)",
        "install.updatesNoClone": "ℹ️ Project folder copied (not cloned with git): no remote updates, only by hand.",
        "install.packagesUnchanged": "✅ Packages unchanged since the last installation",
        "install.updated": "✅ Version {version} installed, programs restarted.",
        "install.display": "Screen: automatic session, no screen blanking, camera and microphone allowed",
        "install.displayManual": "⚠️ raspi-config not available: enable the desktop autologin and disable screen blanking by hand.",
        "install.failed": "❌ Failed during the \"{step}\" step. Details in {log}",
        "install.done": """
╔══════════════════════════════════════════════════════════════╗
║  ✅ INSTALLATION COMPLETE                                     ║
╚══════════════════════════════════════════════════════════════╝
  Raspberry identifier: {device_id}
  Verification code   : {code}

  What is left:
  1. Have this identifier and this code authorized by the server
     administrator (on the server: node admin.js add {device_id} {code})
  2. Scan the QR code above in the app
  3. Reboot the Raspberry (the rights and the screen settings
     only apply after a reboot)
""",
        "install.askReboot": "Reboot now? (y/n): ",
        "install.askGreeting": "\n🔊 A call will be announced, for example: \"Hey grandma, it's Paul calling\".\n   How should the person be called? (grandma, grandpa, mum, dad, their first name...)\n   Enter = none: \"It's Paul calling\": ",
        "install.greeting": "🔊 Call announcement: \"{phrase}\" (GREETING_NAME in config.py to change it)",
        "install.greetingKept": "🔊 Call announcement unchanged: \"{phrase}\" (GREETING_NAME added to config.py)",
        "install.rebooting": "🔄 Rebooting...",
        "install.restarted": "✅ Services restarted. Remember to reboot later (sudo reboot).",
        "switch.noRoot": "❌ Do not run this script with sudo: run it as the Raspberry user.",
        "switch.usage": "Usage: bash switch_server.sh [test | prod]   (no argument: shows the current server)",
        "switch.current": "🌐 Current server: {server}",
        "switch.prodName": "PRODUCTION (wss://appelermami.fr)",
        "switch.testName": "TEST (wss://appelermami.fr:8443, copy of the server for development)",
        "switch.otherName": "other ({url})",
        "switch.noSetting": "❌ SERVER_URL setting not found in {file}.",
        "switch.already": "ℹ️ This Raspberry already uses the {server} server: nothing to change.",
        "switch.done": "✅ This Raspberry now uses the {server} server.",
        "switch.restarting": "🔄 Restarting the agent and the TV page (password asked)...",
        "switch.restarted": "✅ Done. The TV reconnects within about twenty seconds.\n   Check: sudo journalctl -u tv-control -n 15 --no-pager",
    },

    "es": {
        # --- Voice announcement ---
        "tts.phrase": "Oye {greeting}, es {name} quien te llama",
        "tts.phraseNoGreeting": "Es {name} quien te llama",
        "tts.someone": "alguien",

        # --- Agent: refusal by the server ---
        "agent.notAuthorized": """
╔══════════════════════════════════════════════════════════════╗
║  ⛔ ESTA RASPBERRY AÚN NO ESTÁ AUTORIZADA EN EL SERVIDOR       ║
╚══════════════════════════════════════════════════════════════╝
  Identificador : {device_id}
  Código        : {code}
  Servidor      : {server}

  Para usarla, pide al administrador del servidor que la añada
  enviándole este identificador Y este código de verificación
  (node admin.js add {device_id} {code}). Por ejemplo a través de:
    {contact}

  El agente lo reintenta cada {delay} s y se conectará
  automáticamente en cuanto el dispositivo esté autorizado.
""",
        "agent.secretRefused": """
╔══════════════════════════════════════════════════════════════╗
║  ⛔ EL SERVIDOR RECHAZA EL SECRETO DE ESTA RASPBERRY           ║
╚══════════════════════════════════════════════════════════════╝
  Identificador : {device_id}
  El secreto de identity.json no coincide con el que el
  servidor registró para este dispositivo (¿identidad reiniciada?).
  Pide al administrador del servidor que retire y vuelva a
  autorizar este identificador.
  Mensaje del servidor: {message}
""",
        "agent.adminFallback": "el administrador del servidor",
        "agent.stillRefused": "⛔ Sigue rechazada por el servidor ({code})",
        "agent.nowAuthorized": "✅ Dispositivo autorizado por el servidor: conexión establecida",
        "agent.retryUnauthorized": "⏳ Nuevo intento en {delay} s (esperando la autorización del servidor)...",

        # --- Health report (diagnostics.py) ---
        "diag.title": "🩺 Estado de la Raspberry {device_id} ({time})",
        "diag.logs": "Últimos errores de {service}:",
        "diag.noErrors": "(ninguno)",
        "diag.check.system.model": "Modelo",
        "diag.check.system.os": "Sistema",
        "diag.check.system.uptime": "Encendida desde hace (días h:min)",
        "diag.check.service.tvControl": "Servicio del agente (tv-control)",
        "diag.check.service.chromium": "Servicio de la pantalla (chromium-autolaunch)",
        "diag.check.version.chromium": "Versión de Chromium",
        "diag.check.network.server": "Servidor accesible",
        "diag.check.network.interfaces": "Red activa",
        "diag.check.network.wifi": "Señal Wi-Fi",
        "diag.check.system.watchdog": "Watchdog de hardware",
        "diag.check.selfheal": "Reparación automática (estado, última acción, número)",
        "diag.check.version": "Versión instalada",
        "diag.check.update": "Actualizaciones a distancia (estado, última)",
        "diag.check.network.powersave": "Ahorro de energía del Wi-Fi",
        "diag.check.hdmi": "Cable HDMI",
        "diag.check.cec": "TV vista por HDMI-CEC",
        "diag.check.camera": "Cámara",
        "diag.check.microphone": "Micrófono",
        "diag.check.speaker": "Altavoz del timbre",
        "diag.check.mouse": "Ratón (botón para descolgar)",
        "diag.check.disk": "Disco (libre / total)",
        "diag.check.memory": "Memoria (disponible / total)",
        "diag.check.temperature": "Temperatura",
        "diag.check.power": "Alimentación",
        "diag.power.now": "{flag} (ahora)",
        "diag.power.boot": "{flag} (desde el arranque)",
        "diag.flag.underVoltage": "tensión demasiado baja",
        "diag.flag.freqCapped": "frecuencia limitada",
        "diag.flag.throttled": "ralentizada",
        "diag.flag.softTempLimit": "límite de temperatura",

        # --- Identity loading (identity.py) ---
        "identity.fileNotFound": "❌ ¡No se encuentra el archivo {path}!",
        "identity.runSetupFirst": "   Ejecuta primero: python3 setup_identity.py",
        "identity.invalid": "❌ ¡identity.json no es válido!",
        "identity.jsonError": "❌ Error al leer el JSON: {error}",
        "identity.error": "❌ Error: {error}",
        "identity.loaded": "✅ Identidad cargada desde {path}",
        "identity.deviceId": "   Identificador: {device_id}",

        # --- Identity manager (identity_manager.py) ---
        "manager.loading": "📂 Cargando la identidad desde {path}",
        "manager.loaded": "✅ Identidad cargada: {device_id}",
        "manager.notFoundGenerating": "🆕 No se ha encontrado ninguna identidad, generando...",
        "manager.created": "✅ Identidad creada: {device_id}",
        "manager.saved": "💾 Identidad guardada (escritura atómica): {path}",
        "manager.permissions": "   Permisos: 0o600 (solo el propietario del archivo)",
        "manager.saveError": "❌ Error al guardar: {error}",
        "manager.corrupted": "❌ Archivo identity.json dañado: {error}",
        "manager.fileNotFound": "❌ Archivo no encontrado: {path}",
        "manager.title": "📱 IDENTIDAD DE LA RASPBERRY",
        "manager.idLabel": "  raspberryId  : {value}",
        "manager.createdLabel": "  createdAt    : {value}",
        "manager.secretLabel": "  deviceSecret : {value}",
        "manager.secretMasked": "  deviceSecret : {value} (oculto)",
        "manager.codeLabel": "  code         : {value} (código de verificación, para el administrador)",
        "manager.backup": "💾 Copia de seguridad de la identidad anterior: {path}",
        "manager.generatingNew": "🔄 Generando una nueva identidad...",
        "manager.newIdentity": "✅ Nueva identidad: {device_id}",
        "manager.confirmReset": "⚠️  ¿Seguro que quieres reiniciar la identidad? (s/n): ",
        "manager.cancelled": "❌ Cancelado",
        "manager.unknownCommand": "❌ Comando desconocido: {command}",
        "manager.usage": """Uso:
  python3 identity_manager.py --show          (muestra el ID, oculta el secreto)
  python3 identity_manager.py --show-secret   (muestra el ID Y el secreto)
  python3 identity_manager.py --reset         (nueva identidad, copia .bak)""",

        # --- First setup (setup_identity.py) ---
        "setup.title": "🚀 CONFIGURACIÓN DE LA IDENTIDAD DE LA RASPBERRY PI",
        "setup.exists": "✅ Ya existe una identidad.\n",
        "setup.askReset": "¿Quieres reiniciarla? (s/n): ",
        "setup.resetDone": "\n✅ Reinicio completado",
        "setup.backupKept": "   (identidad anterior guardada como .bak)\n",
        "setup.cancelled": "❌ Cancelado, se conserva la identidad\n",
        "setup.generatingFirst": "🆕 Generando la primera identidad...\n",
        "setup.done": "\n✅ ¡Configuración completada!",
        "setup.file": "   Archivo: {path}",
        "setup.permissions": "   Permisos: 0o600 (solo el propietario del archivo)",
        "setup.permanent": "   Esta identidad es PERMANENTE\n",
        "setup.nextSteps": """ℹ️  Próximos pasos:
   1. 📨 Enviar el ID y el código de verificación al administrador
      del servidor para que autorice esta Raspberry — nunca el secreto
   2. 📡 Iniciar el agente: se conecta en cuanto el ID esté autorizado
   3. 📱 Escanear el código QR en la aplicación para añadir el contacto""",
        "setup.qrSaved": "✅ Código QR guardado: {path}",
        "setup.qrFile": """
╔════════════════════════════════════════════════════════════════╗
║                LLAMAR A LA ABUELA - INSTALACIÓN               ║
╚════════════════════════════════════════════════════════════════╝

📱 IDENTIFICADOR DE LA RASPBERRY (PARA ESCANEAR)
{qr}
📝 Identificador (para copiar a mano): {device_id}
🔑 Código de verificación: {code}
   (para dar al administrador con el identificador; no es el secreto)

El código secreto se guarda por separado en identity.json.
No lo compartas con nadie: nunca sale de esta Raspberry.

╔════════════════════════════════════════════════════════════════╗
║                    PRÓXIMOS PASOS                             ║
╚════════════════════════════════════════════════════════════════╝

1. 📨 Enviar el ID y el código de verificación al administrador del
   servidor para que autorice esta Raspberry
   (node admin.js add {device_id} {code})
2. 📡 Iniciar el agente: se conecta en cuanto el ID esté autorizado
3. 📱 Escanear este código QR en la aplicación para añadir el contacto
""",

        # --- install.sh ---
        "install.title": "🚀 INSTALACIÓN DE LLAMAR A LA ABUELA EN ESTA RASPBERRY",
        "install.noRoot": "❌ No ejecutes este script con sudo: ejecútalo con el usuario de la Raspberry (la contraseña se pedirá cuando haga falta).",
        "install.sudo": "🔑 Se va a pedir la contraseña del usuario (permisos de administrador).",
        "install.checks": "Comprobaciones",
        "install.noInternet": "❌ Sin conexión a internet: comprueba el Wi-Fi y vuelve a ejecutar el script.",
        "install.noDesktop": "⚠️ No se detecta escritorio: Chromium no podrá mostrarse en el televisor. Hace falta Raspberry Pi OS con escritorio.",
        "install.askContinue": "¿Continuar de todos modos? (s/n): ",
        "install.stopped": "❌ Instalación detenida.",
        "install.packages": "Paquetes del sistema (unos minutos)",
        "install.files": "Archivos del proyecto en {dir}",
        "install.configKept": "   Ajustes existentes conservados (archivo antiguo: {backup})",
        "install.mouseReset": "   MOUSE_DEVICE = {old} (ruta inestable) sustituido por la detección automática",
        "install.python": "Entorno Python",
        "install.ringtone": "Tono de llamada",
        "install.groups": "Permisos del usuario (ratón, TV, sonido)",
        "install.identity": "Identidad de la Raspberry",
        "install.identityKept": "   Identidad existente conservada: {device_id}",
        "install.services": "Arranque automático (agente y pantalla)",
        "install.selfheal": "Reparación automática (Wi-Fi, pantalla, agente, reinicio nocturno)",
        "install.updates": "Actualizaciones a distancia (solo versiones firmadas)",
        "install.updatesNoClone": "ℹ️ Carpeta del proyecto copiada (no clonada con git): sin actualizaciones a distancia, solo a mano.",
        "install.packagesUnchanged": "✅ Paquetes sin cambios desde la última instalación",
        "install.updated": "✅ Versión {version} instalada, programas reiniciados.",
        "install.display": "Pantalla: sesión automática, sin reposo de pantalla, cámara y micrófono permitidos",
        "install.displayManual": "⚠️ raspi-config no disponible: activa a mano el inicio de sesión automático en el escritorio y desactiva el reposo de la pantalla.",
        "install.failed": "❌ Fallo durante el paso «{step}». Detalles en {log}",
        "install.done": """
╔══════════════════════════════════════════════════════════════╗
║  ✅ INSTALACIÓN TERMINADA                                     ║
╚══════════════════════════════════════════════════════════════╝
  Identificador de la Raspberry: {device_id}
  Código de verificación       : {code}

  Queda por hacer:
  1. Que el administrador del servidor autorice este identificador
     y este código (en el servidor: node admin.js add {device_id} {code})
  2. Escanear el código QR de arriba en la aplicación
  3. Reiniciar la Raspberry (los permisos y la pantalla solo se
     aplican después de reiniciar)
""",
        "install.askReboot": "¿Reiniciar ahora? (s/n): ",
        "install.askGreeting": "\n🔊 Una llamada se anunciará, por ejemplo: «Oye abuela, es Paul quien te llama».\n   ¿Cómo llamar a la persona? (abuela, abuelo, mamá, papá, su nombre...)\n   Intro = sin: «Es Paul quien te llama»: ",
        "install.greeting": "🔊 Anuncio de una llamada: «{phrase}» (GREETING_NAME en config.py para cambiarlo)",
        "install.greetingKept": "🔊 Anuncio de una llamada sin cambios: «{phrase}» (GREETING_NAME añadido en config.py)",
        "install.rebooting": "🔄 Reiniciando...",
        "install.restarted": "✅ Servicios reiniciados. Recuerda reiniciar más tarde (sudo reboot).",
        "switch.noRoot": "❌ No ejecutes este script con sudo: ejecútalo con el usuario de la Raspberry.",
        "switch.usage": "Uso: bash switch_server.sh [test | prod]   (sin argumento: muestra el servidor actual)",
        "switch.current": "🌐 Servidor actual: {server}",
        "switch.prodName": "PRODUCCIÓN (wss://appelermami.fr)",
        "switch.testName": "PRUEBA (wss://appelermami.fr:8443, copia del servidor para el desarrollo)",
        "switch.otherName": "otro ({url})",
        "switch.noSetting": "❌ No se encuentra el ajuste SERVER_URL en {file}.",
        "switch.already": "ℹ️ Esta Raspberry ya usa el servidor {server}: nada que cambiar.",
        "switch.done": "✅ Esta Raspberry usa ahora el servidor {server}.",
        "switch.restarting": "🔄 Reiniciando el agente y la página de la TV (se pide la contraseña)...",
        "switch.restarted": "✅ Hecho. La TV se reconecta en unos veinte segundos.\n   Comprobación: sudo journalctl -u tv-control -n 15 --no-pager",
    },
}

# Answers accepted as "yes" to the (y/n) questions, whatever the language
YES_ANSWERS = ("y", "o", "s", "yes", "oui", "si", "sí")


def language():
    """Language configured in config.py, or French if it is not supported."""
    lang = str(getattr(config, "LANGUAGE", "fr")).strip().lower()[:2]
    return lang if lang in SUPPORTED_LANGUAGES else "fr"


def t(key, **params):
    """Translates a key and replaces the {placeholders} with the parameters."""
    template = MESSAGES[language()].get(key) or MESSAGES["en"].get(key) or key
    return template.format(**params) if params else template


def is_yes(answer):
    """True if the answer to a (y/n) question means "yes"."""
    return answer.strip().lower() in YES_ANSWERS
