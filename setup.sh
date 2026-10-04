#!/usr/bin/env bash
# Symlinks these configs into ~/.config on a fresh machine.
# Run from anywhere after cloning this repo to ~/boop-config.
set -e
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HOME/.config" "$HOME/.local/bin" "$HOME/.local/libexec/zellij-editor"

for d in i3 polybar picom kitty ghostty zellij micro leaf scripts; do
  target="$HOME/.config/$d"
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    echo "SKIP $d: $target already exists and is not a symlink"
    continue
  fi
  ln -sfn "$REPO/config/$d" "$target"
  echo "linked $d"
done

# Install smart floating opener for Zellij (Alt/Cmd+Shift+M and OSC 8 link opener)
chmod +x "$REPO/config/scripts/zellij-open-smart" "$REPO/config/scripts/patch-leaf-ctrl-q.py"
ln -sfn "$REPO/config/scripts/zellij-open-smart" "$HOME/.local/bin/zellij-open-smart"
ln -sfn "$REPO/config/scripts/zellij-open-smart" "$HOME/.local/libexec/zellij-editor/nvim"
echo "linked zellij-open-smart -> ~/.local/bin/zellij-open-smart"

# Patch leaf binary (if installed) so Ctrl+Q quits leaf like micro
if command -v leaf >/dev/null 2>&1 || [ -f "$HOME/.local/bin/leaf" ]; then
  python3 "$REPO/config/scripts/patch-leaf-ctrl-q.py" || true
fi
