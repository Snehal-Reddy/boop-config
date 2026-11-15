#!/usr/bin/env python3
"""Event-driven smart workspace & window list module for Polybar + i3."""

import json
import subprocess
import time

# Color palette (Smoked Glass)
C_BG_FOCUS = "#363F54"
C_FG_FOCUS = "#F3F6FC"
C_ACCENT = "#89B4FA"
C_OCCUPIED = "#D8DEE9"
C_EMPTY = "#656D82"
C_URGENT = "#F38BA8"
C_GREEN = "#A6E3A1"
C_AMBER = "#E5C07B"

# Fixed character width for the text portion of every workspace pill
LABEL_WIDTH = 10

# FontAwesome 4.7 icons
ICON_CHROME = "\uf268"
ICON_TERM = "\uf120"
ICON_CODE = "\uf121"
ICON_SPOTIFY = "\uf1bc"
ICON_OBSIDIAN = "\uf249"
ICON_WEB = "\uf0ac"
ICON_SETTINGS = "\uf013"
ICON_FILES = "\uf07b"
ICON_AUDIO = "\uf028"
ICON_WINDOW = "\uf2d0"
ICON_SHIELD = "\uf132"

# Workspaces that always remain visible as static anchors
STATIC_WORKSPACES = {
    1: ("Chrome", ICON_CHROME, C_ACCENT),
    2: ("Dev", ICON_CODE, C_ACCENT),
    3: ("Zellij", ICON_TERM, C_ACCENT),
    5: ("Spotify", ICON_SPOTIFY, C_GREEN),
}

# Known window class -> (short label, icon)
CLASS_MAP = {
    "google-chrome": ("Chrome", ICON_CHROME),
    "chromium": ("Chrome", ICON_CHROME),
    "brave-browser": ("Brave", ICON_WEB),
    "firefox": ("Firefox", ICON_WEB),
    "kitty": ("Zellij", ICON_TERM),
    "alacritty": ("Term", ICON_TERM),
    "cursor": ("Cursor", ICON_CODE),
    "code": ("Code", ICON_CODE),
    "spotify": ("Spotify", ICON_SPOTIFY),
    "obsidian": ("Obsidian", ICON_OBSIDIAN),
    "gnome-control-center": ("Settings", ICON_SETTINGS),
    "xfce4-settings-manager": ("Settings", ICON_SETTINGS),
    "org.gnome.nautilus": ("Files", ICON_FILES),
    "thunar": ("Files", ICON_FILES),
    "pavucontrol": ("Audio", ICON_AUDIO),
}


def run_i3_json(msg_type: str):
    out = subprocess.check_output(["i3-msg", "-t", msg_type], text=True)
    return json.loads(out)


def classify_window(win_props: dict):
    cls = (win_props.get("class") or "").strip()
    cls_lower = cls.lower()
    if cls_lower in CLASS_MAP:
        return CLASS_MAP[cls_lower]
    for key, val in CLASS_MAP.items():
        if key in cls_lower:
            return val
    short = cls.split(".")[-1] if cls else "App"
    short = short.replace("-browser", "").replace("-desktop", "")
    return (short.capitalize() if short else "App", ICON_WINDOW)


def collect_workspace_windows(tree: dict) -> dict:
    """Return mapping: workspace_name -> list of (label, icon, cls_lower)."""
    ws_windows = {}

    def walk(node, current_ws=None):
        if node.get("type") == "workspace":
            current_ws = node.get("name")
            ws_windows.setdefault(current_ws, [])
        if current_ws and node.get("window") and node.get("window_properties"):
            props = node["window_properties"]
            cls_lower = (props.get("class") or "").lower()
            if cls_lower != "polybar":
                label, icon = classify_window(props)
                ws_windows[current_ws].append((label, icon, cls_lower))
        for child in node.get("nodes", []) + node.get("floating_nodes", []):
            walk(child, current_ws)

    walk(tree)
    return ws_windows


def fit_label(prefix: str, app_name: str, suffix: str = "") -> str:
    """Fit '<prefix> <app_name><suffix>' into exactly LABEL_WIDTH characters."""
    budget = LABEL_WIDTH - len(prefix) - 1 - len(suffix)
    if budget < 1:
        raw = f"{prefix} {app_name}{suffix}"
        return raw[: LABEL_WIDTH - 1] + "…" if len(raw) > LABEL_WIDTH else f"{raw:<{LABEL_WIDTH}}"

    if len(app_name) > budget:
        trimmed = app_name[: max(1, budget - 1)] + "…"
    else:
        trimmed = app_name

    text = f"{prefix} {trimmed}{suffix}"
    return f"{text:<{LABEL_WIDTH}}"


def summarize_apps(num_str: str, apps: list) -> tuple[str, str]:
    """Summarize windows on a workspace into (fixed_width_text, icon_override)."""
    if not apps:
        return ("", "")
    counts = {}
    icons = {}
    order = []
    for label, icon, _ in apps:
        if label not in counts:
            counts[label] = 0
            icons[label] = icon
            order.append(label)
        counts[label] += 1

    primary = order[0]
    extra_apps = len(order) - 1
    if extra_apps > 0:
        suffix = f"+{extra_apps}"
    elif counts[primary] > 1:
        suffix = f"×{counts[primary]}"
    else:
        suffix = ""

    return (fit_label(num_str, primary, suffix), icons[primary])


def format_workspace(ws: dict, apps: list) -> str | None:
    num = ws.get("num", -1)
    name = ws.get("name", "")
    focused = ws.get("focused", False)
    occupied = len(apps) > 0

    is_static = num in STATIC_WORKSPACES
    if not is_static and not occupied and not focused:
        return None

    num_str = str(num) if num >= 0 else name[:2]

    if is_static:
        default_label, default_icon, accent_color = STATIC_WORKSPACES[num]
        if occupied:
            text, first_icon = summarize_apps(num_str, apps)
            icon = first_icon or default_icon
        else:
            icon = default_icon
            text = fit_label(num_str, default_label)
    elif num == 6:
        accent_color = C_ACCENT
        if occupied:
            text, first_icon = summarize_apps(num_str, apps)
            icon = first_icon or ICON_OBSIDIAN
        else:
            icon = ICON_OBSIDIAN
            text = fit_label("6", "Obsidian")
    else:
        accent_color = C_AMBER
        if occupied:
            text, first_icon = summarize_apps(num_str, apps)
            icon = first_icon or (ICON_SHIELD if num == 4 else ICON_WINDOW)
        else:
            icon = ICON_SHIELD if num == 4 else ICON_WINDOW
            clean_name = name.split(":", 1)[-1].strip() if ":" in name else "Misc"
            text = fit_label(num_str, clean_name or "Misc")

    mono_text = f"%{{T3}}{text}%{{T-}}"

    if focused:
        chunk = (
            f"%{{B{C_BG_FOCUS}}}%{{F{accent_color}}} {icon}%{{F{C_FG_FOCUS}}} {mono_text} %{{B-}}%{{F-}}"
        )
    elif occupied:
        chunk = f"%{{F{accent_color}}} {icon}%{{F{C_OCCUPIED}}} {mono_text} %{{F-}}"
    else:
        chunk = f"%{{F{C_EMPTY}}} {icon} {mono_text} %{{F-}}"

    if num and num > 0:
        action = f"i3-msg -q workspace number {num}"
    else:
        safe_name = name.replace("\\", "\\\\").replace(":", "\\:").replace("'", "'\"'\"'")
        action = f"i3-msg -q workspace '{safe_name}'"
    return f"%{{A1:{action}:}}{chunk}%{{A}}"


def render():
    workspaces = run_i3_json("get_workspaces")
    tree = run_i3_json("get_tree")
    ws_windows = collect_workspace_windows(tree)

    # Deduplicate workspaces that share a number (e.g. accidental "1" alongside "1: Web"):
    # prefer occupied workspaces over empty duplicates.
    occupied_nums = {
        ws.get("num")
        for ws in workspaces
        if ws.get("num", -1) > 0 and ws_windows.get(ws.get("name"))
    }

    rendered = []
    for ws in sorted(workspaces, key=lambda w: (w.get("num", 999), w.get("name", ""))):
        num = ws.get("num", -1)
        apps = ws_windows.get(ws.get("name"), [])
        if num in occupied_nums and not apps:
            continue
        item = format_workspace(ws, apps)
        if item:
            rendered.append(item)

    print(" ".join(rendered), flush=True)


def main():
    while True:
        try:
            render()
            proc = subprocess.Popen(
                ["i3-msg", "-t", "subscribe", "-m", '["workspace","window"]'],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            assert proc.stdout is not None
            for _ in proc.stdout:
                render()
            proc.wait()
        except Exception:
            pass
        time.sleep(0.4)


if __name__ == "__main__":
    main()
