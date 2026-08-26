#!/usr/bin/env bash
# Symlinks these configs into ~/.config on a fresh machine.
# Run from anywhere after cloning this repo to ~/boop-config.
set -e
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HOME/.config"
for d in i3 polybar picom kitty ghostty zellij micro scripts; do
  target="$HOME/.config/$d"
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    echo "SKIP $d: $target already exists and is not a symlink"
    continue
  fi
  ln -sfn "$REPO/config/$d" "$target"
  echo "linked $d"
done
