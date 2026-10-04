#!/bin/bash
# Pick or create a zellij "workspace" session via rofi, in its own kitty window.
# New workspace names get prompted for a project directory, fuzzy-filtered
# against dirs up to 3 levels under $HOME (used as the first pane's cwd);
# existing ones just attach/resurrect as-is.

set -euo pipefail

export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"

existing=$(zellij list-sessions --short --no-formatting 2>/dev/null || true)

choice=$(printf '%s\n' "$existing" | rofi -dmenu -p "workspace")
[ -z "$choice" ] && exit 0

dir_args=()
if ! printf '%s\n' "$existing" | grep -qxF "$choice"; then
    dir_list=$(find "$HOME" -mindepth 1 -maxdepth 3 -type d \
        \( -name ".*" -o -name node_modules -o -name target -o -name dist \
           -o -name build -o -name __pycache__ -o -name venv -o -name .venv \) -prune \
        -o -type d -print 2>/dev/null | sort)
    dir=$(printf '%s\n' "$dir_list" | rofi -dmenu -matching fuzzy -p "project directory for '$choice'")
    dir="${dir:-$HOME}"
    dir="${dir/#\~/$HOME}"
    mkdir -p "$dir"
    dir_args=(--directory "$dir")
fi

exec kitty --title "zellij: $choice" "${dir_args[@]}" -- zellij attach --create --force-run-commands "$choice"
