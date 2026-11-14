#!/usr/bin/env python3
"""Compact Spotify MPRIS status for the centered Polybar pill."""

import re
import subprocess

MAX_LEN = 28


def get_prop(prop: str) -> str:
    try:
        return subprocess.check_output(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                "org.mpris.MediaPlayer2.spotify",
                "--object-path",
                "/org/mpris/MediaPlayer2",
                "--method",
                "org.freedesktop.DBus.Properties.Get",
                "org.mpris.MediaPlayer2.Player",
                prop,
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return ""


def main():
    status_raw = get_prop("PlaybackStatus")
    if not status_raw:
        print("", flush=True)
        return

    status = "Playing" if "Playing" in status_raw else ("Paused" if "Paused" in status_raw else "")
    if not status:
        print("", flush=True)
        return

    meta = get_prop("Metadata")
    artist_m = re.search(r"'xesam:artist': <\[([^\]]+)\]>", meta)
    title_m = re.search(r"'xesam:title': <'((?:\\'|[^'])*)'>", meta)

    artist = ""
    if artist_m:
        first = re.search(r"'((?:\\'|[^'])*)'", artist_m.group(1))
        if first:
            artist = first.group(1).replace("\\'", "'")

    title = title_m.group(1).replace("\\'", "'") if title_m else ""
    label = f"{artist} - {title}" if artist and title else (title or artist)
    if not label:
        print("", flush=True)
        return

    if len(label) > MAX_LEN:
        label = label[: MAX_LEN - 1].rstrip(" -–") + "…"

    # Escape Polybar % formatting characters
    label = label.replace("%", "%%")

    if status == "Playing":
        print(f"%{{F#A6E3A1}}%{{F-}} {label}  %{{F#4C5368}}|%{{F-}}  ", flush=True)
    else:
        print(f"%{{F#7F849C}} {label}%{{F-}}  %{{F#4C5368}}|%{{F-}}  ", flush=True)


if __name__ == "__main__":
    main()
