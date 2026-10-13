#!/bin/bash
# Go to the folder of this script (~/AppelerMamie on the Raspberry)
cd "$(dirname "$0")"

# Activate the Python virtual environment
source ./venv/bin/activate

# Start the agent
python3 main.py
