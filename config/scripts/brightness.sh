#!/bin/bash

# Configuration
MONITOR="HDMI-0"
STEP=0.05
MIN=0.1
MAX=1.0

# Get current brightness
CURRENT=$(xrandr --verbose | grep -m 1 "Brightness" | cut -d ' ' -f 2)

if [ "$1" == "up" ]; then
    NEW=$(echo "$CURRENT + $STEP" | bc)
    if (( $(echo "$NEW > $MAX" | bc -l) )); then NEW=$MAX; fi
elif [ "$1" == "down" ]; then
    NEW=$(echo "$CURRENT - $STEP" | bc)
    if (( $(echo "$NEW < $MIN" | bc -l) )); then NEW=$MIN; fi
else
    echo "Usage: $0 {up|down}"
    exit 1
fi

# Apply the new brightness
xrandr --output $MONITOR --brightness $NEW
