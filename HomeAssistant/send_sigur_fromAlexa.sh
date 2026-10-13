#!/bin/bash
# Accepts the current call remotely by sending SIGUSR1 to the agent
# (for example from Home Assistant / Alexa).

PATTERN='main.py'
PID=$(pgrep -f "$PATTERN")

if [ -z "$PID" ]; then
    echo "❌ No main.py process found"
    exit 1
fi

# Refuse to send the signal if several processes match
COUNT=$(printf '%s\n' "$PID" | wc -l)
if [ "$COUNT" -ne 1 ]; then
    echo "❌ Several processes match:"
    pgrep -af "$PATTERN"
    exit 1
fi

echo "📡 Sending SIGUSR1 to process $PID"
kill -USR1 "$PID" && echo "✅ Signal sent"
