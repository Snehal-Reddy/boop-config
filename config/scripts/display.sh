#!/bin/bash

# Configuration
MONITOR="HDMI-0"
STATE_FILE="$HOME/.cache/display_state"
STEP=0.05
MIN=0.1
MAX=1.0
NIGHT_TEMP=3000
DAY_TEMP=6500 # Neutral color

# Load current state or set defaults
if [ -f "$STATE_FILE" ]; then
    source "$STATE_FILE"
else
    BRIGHTNESS=1.0
    NIGHT_MODE="on"
fi

case "$1" in
    up)
        BRIGHTNESS=$(echo "$BRIGHTNESS + $STEP" | bc)
        if (( $(echo "$BRIGHTNESS > $MAX" | bc -l) )); then BRIGHTNESS=$MAX; fi
        ;;
    down)
        BRIGHTNESS=$(echo "$BRIGHTNESS - $STEP" | bc)
        if (( $(echo "$BRIGHTNESS < $MIN" | bc -l) )); then BRIGHTNESS=$MIN; fi
        ;;
    toggle)
        if [ "$NIGHT_MODE" == "on" ]; then
            NIGHT_MODE="off"
        else
            NIGHT_MODE="on"
        fi
        ;;
    apply)
        # Just apply current settings (for startup)
        ;;
esac

# Save state
echo "BRIGHTNESS=$BRIGHTNESS" > "$STATE_FILE"
echo "NIGHT_MODE=$NIGHT_MODE" >> "$STATE_FILE"

# Apply settings
if [ "$NIGHT_MODE" == "on" ]; then
    # Apply warm temperature + brightness
    gammastep -m randr -O $NIGHT_TEMP -b $BRIGHTNESS:$BRIGHTNESS > /dev/null 2>&1
else
    # Apply neutral temperature + brightness
    gammastep -m randr -O $DAY_TEMP -b $BRIGHTNESS:$BRIGHTNESS > /dev/null 2>&1
fi
