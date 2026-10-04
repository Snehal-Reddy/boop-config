#!/usr/bin/env bash
# zellij-cloud-workspace.sh
# Interactive project & session picker for Cloudtop using fzf & Zellij

set -euo pipefail

# Ensure TERM is valid for curses/fzf/zellij
export TERM="${TERM:-xterm-256color}"

# Ensure ~/.cargo/bin is in PATH for zellij
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"

RECENT_FILE="$HOME/.config/zellij/recent_projects"
mkdir -p "$(dirname "$RECENT_FILE")"
touch "$RECENT_FILE"

# Pre-populate known roots if recent file is empty
if [ ! -s "$RECENT_FILE" ]; then
    for default_dir in "$HOME/laj/bootloader" "$HOME/laj/android" "$HOME/laj/kernel" "$HOME/trusty"; do
        if [ -d "$default_dir" ]; then
            echo "$default_dir" >> "$RECENT_FILE"
        fi
    done
fi

# Function to get active / existing sessions
get_sessions() {
    zellij list-sessions --short --no-formatting 2>/dev/null || true
}

# Function to sanitize session name from path or string
make_session_name() {
    local target="$1"
    # If it's a directory path, use relative path or clean name
    target="${target/#$HOME\//}"
    target="${target//\//-}"
    target="${target//./-}"
    target="${target// /_}"
    target="${target#-}"
    target="${target%-}"
    [ -z "$target" ] && target="main"
    echo "$target"
}

# Collect options for fzf
collect_options() {
    local sessions
    sessions=$(get_sessions)

    # 1. Active / resurrectable Zellij sessions
    if [ -n "$sessions" ]; then
        while IFS= read -r s; do
            [ -n "$s" ] && echo "[session] $s"
        done <<< "$sessions"
    fi

    # 2. Recent project directories
    if [ -s "$RECENT_FILE" ]; then
        while IFS= read -r p; do
            [ -n "$p" ] && echo "[project] $p"
        done < <(sort -u "$RECENT_FILE")
    fi

    # 3. Discovered project directories (laj subdirectories, trusty, etc.)
    for base in "$HOME/laj" "$HOME/trusty" "$HOME/src" "$HOME/workspace"; do
        if [ -d "$base" ]; then
            echo "[project] $base"
            for sub in "$base"/*; do
                if [ -d "$sub" ] && [ "$(basename "$sub")" != "out" ] && [ "$(basename "$sub")" != "build-root" ]; then
                    echo "[project] $sub"
                fi
            done
        fi
    done
}

# Direct argument passed? (e.g. zellij-cloud-workspace.sh trusty)
if [ $# -ge 1 ] && [ -n "$1" ]; then
    input_target="$1"
    
    # Check if it's an existing session
    if get_sessions | grep -qxF "$input_target"; then
        exec zellij attach "$input_target" --force-run-commands
    fi

    # Check if it's a directory path
    dir="${input_target/#\~/$HOME}"
    if [ -d "$dir" ]; then
        session_name=$(make_session_name "$dir")
        # Save to recent
        grep -qxF "$dir" "$RECENT_FILE" 2>/dev/null || echo "$dir" >> "$RECENT_FILE"
        cd "$dir"
        exec zellij attach --create "$session_name" --force-run-commands
    fi

    # Otherwise treat as new session name in HOME
    exec zellij attach --create "$input_target" --force-run-commands
fi

# Deduplicate and present via fzf
selected=$(collect_options | awk '!seen[$0]++' | fzf \
    --height=70% \
    --layout=reverse \
    --border=rounded \
    --prompt="🚀 Cloudtop Project > " \
    --header="[Enter] Attach/Open | [Type Path] Custom directory or session | [Esc] Exit" \
    --print-query || true)

[ -z "$selected" ] && exit 0

# fzf --print-query outputs query on line 1, selection on line 2 (if any)
query=$(echo "$selected" | sed -n '1p')
choice=$(echo "$selected" | sed -n '2p')

# If no selection made from list, use the query string
target="${choice:-$query}"
[ -z "$target" ] && exit 0

if [[ "$target" == "[session] "* ]]; then
    session_name="${target#\[session\] }"
    exec zellij attach "$session_name" --force-run-commands
fi

if [[ "$target" == "[project] "* ]]; then
    dir="${target#\[project\] }"
    dir="${dir/#\~/$HOME}"
    session_name=$(make_session_name "$dir")
    grep -qxF "$dir" "$RECENT_FILE" 2>/dev/null || echo "$dir" >> "$RECENT_FILE"
    cd "$dir"
    exec zellij attach --create "$session_name" --force-run-commands
fi

# Custom query typed by user
if [[ "$target" == "~"* ]] || [[ "$target" == "/"* ]] || [[ "$target" == *"/"* ]]; then
    dir="${target/#\~/$HOME}"
    mkdir -p "$dir"
    session_name=$(make_session_name "$dir")
    grep -qxF "$dir" "$RECENT_FILE" 2>/dev/null || echo "$dir" >> "$RECENT_FILE"
    cd "$dir"
    exec zellij attach --create "$session_name" --force-run-commands
else
    # Plain name typed
    session_name="$target"
    exec zellij attach --create "$session_name" --force-run-commands
fi
