#!/usr/bin/env python3
"""Event-driven PipeWire/PulseAudio volume module for Polybar via pactl subscribe."""

import re
import subprocess
import time


def render():
    try:
        v_out = subprocess.check_output(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"], text=True, stderr=subprocess.DEVNULL
        )
        m_out = subprocess.check_output(
            ["pactl", "get-sink-mute", "@DEFAULT_SINK@"], text=True, stderr=subprocess.DEVNULL
        )
    except Exception:
        print("%{F#F38BA8} --%{F-}", flush=True)
        return

    muted = "yes" in m_out.lower()
    m = re.search(r"(\d+)%", v_out)
    pct = int(m.group(1)) if m else 0

    if muted:
        print("%{F#F38BA8} muted%{F-}", flush=True)
        return

    if pct == 0:
        icon = ""
    elif pct < 50:
        icon = ""
    else:
        icon = ""

    print(f"%{{F#89B4FA}}{icon}%{{F-}} {pct}%", flush=True)


def main():
    while True:
        try:
            render()
            proc = subprocess.Popen(
                ["pactl", "subscribe"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                if "sink" in line or "server" in line:
                    render()
            proc.wait()
        except Exception:
            pass
        time.sleep(0.5)


if __name__ == "__main__":
    main()
