#!/bin/bash
# Health report of the Raspberry ("état des lieux"): services, network, TV,
# camera, sound, mouse, disk, temperature, power and last errors.
# Usage: ./diagnose.sh          (text, in the language of config.py)
#        ./diagnose.sh --json   (raw report, as sent to the server)
# The server administrator can get the same report remotely:
#        node admin.js diagnose <raspberry id>

# Go to the folder of this script (~/AppelerMamie on the Raspberry)
cd "$(dirname "$0")"

./venv/bin/python3 diagnostics.py "$@"
