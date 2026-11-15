#!/usr/bin/env bash
# Symlinks these configs into ~/.config on a fresh machine.
# Run from anywhere after cloning this repo to ~/boop-config.
set -e
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HOME/.config" "$HOME/.local/bin" "$HOME/.local/libexec/zellij-editor" "$HOME/.config/systemd/user"

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

# Install agy-in-Zellij session resurrection helpers and systemd user watcher
for script in agy-zellij-discover agy-zellij-sync agy-zellij-watch agy-resurrect; do
  chmod +x "$REPO/config/scripts/$script"
  ln -sfn "$REPO/config/scripts/$script" "$HOME/.local/bin/$script"
  echo "linked $script -> ~/.local/bin/$script"
done

ln -sfn "$REPO/config/systemd/user/agy-zellij-watch.service" "$HOME/.config/systemd/user/agy-zellij-watch.service"
echo "linked agy-zellij-watch.service -> ~/.config/systemd/user/agy-zellij-watch.service"

if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  systemctl --user daemon-reload
  systemctl --user enable agy-zellij-watch.service
  systemctl --user restart agy-zellij-watch.service
  echo "enabled and restarted agy-zellij-watch.service"
else
  echo "NOTE: systemctl --user not reachable here; enable later with: systemctl --user enable --now agy-zellij-watch.service"
fi

# Patch leaf binary (if installed) so Ctrl+Q quits leaf like micro
if command -v leaf >/dev/null 2>&1 || [ -f "$HOME/.local/bin/leaf" ]; then
  python3 "$REPO/config/scripts/patch-leaf-ctrl-q.py" || true
fi
