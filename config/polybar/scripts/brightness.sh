#!/bin/bash
# Reads current xrandr software brightness for HDMI-0 (matches ~/.config/scripts/brightness.sh).

val=$(xrandr --verbose 2>/dev/null | awk '/Brightness:/ {print $2; exit}')
if [ -z "$val" ]; then
    echo " --%"
    exit 0
fi

pct=$(awk -v b="$val" 'BEGIN { printf "%.0f", b * 100 }')
echo "%{F#E5C07B}%{F-} ${pct}%"
