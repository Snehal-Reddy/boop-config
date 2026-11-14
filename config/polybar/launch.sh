#!/usr/bin/env bash

# Terminate already running bar instances and helper scripts
killall -q polybar
pkill -f "polybar/scripts/i3_windows.py" 2>/dev/null || true
pkill -f "polybar/scripts/audio_status.py" 2>/dev/null || true

# Wait until the processes have been shut down
while pgrep -u "$UID" -x polybar >/dev/null; do sleep 0.3; done

# Launch the Smoked Glass floating pill bar detached from the calling shell
nohup polybar main > /tmp/polybar.log 2>&1 </dev/null &
disown

echo "Polybar launched..."
