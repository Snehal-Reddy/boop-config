#!/bin/bash
# Pick or create a zellij "workspace" session via rofi, in its own kitty window.
# New workspace names get prompted for a project directory (used as the
# first pane's cwd); existing ones just attach/resurrect as-is.

set -euo pipefail

export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"

existing=$(zellij list-sessions --short --no-formatting 2>/dev/null || true)

choice=$(printf '%s\n' "$existing" | rofi -dmenu -p "workspace")
[ -z "$choice" ] && exit 0

dir_args=()
if ! printf '%s\n' "$existing" | grep -qxF "$choice"; then
    dir=$(printf '%s\n' "$HOME" | rofi -dmenu -p "project directory for '$choice'")
    dir="${dir:-$HOME}"
    dir="${dir/#\~/$HOME}"
    mkdir -p "$dir"
    dir_args=(--directory "$dir")
fi

exec kitty --title "zellij: $choice" "${dir_args[@]}" -- zellij attach --create --force-run-commands "$choice"
