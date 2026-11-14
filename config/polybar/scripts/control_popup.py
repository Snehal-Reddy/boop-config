#!/usr/bin/env python3
"""Smoked Glass GTK3 floating control popup for Polybar (brightness & audio)."""

import os
import re
import signal
import subprocess
import sys
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk

PID_FILE = "/tmp/polybar-control-popup.pid"
MONITOR = "HDMI-0"
POPUP_WIDTH = 276

CSS = b"""
window#polybar-control {
    background-color: rgba(17, 19, 26, 0.90);
    border: 1px solid #363F54;
    border-radius: 12px;
    color: #E6E9EF;
    font-family: "Noto Sans", sans-serif;
    font-size: 10pt;
}
.header-title {
    font-weight: bold;
    color: #E6E9EF;
}
.header-value {
    color: #89B4FA;
    font-weight: bold;
}
scale trough {
    min-height: 8px;
    border-radius: 4px;
    background-color: #262B3A;
}
scale highlight {
    min-height: 8px;
    border-radius: 4px;
    background-color: #89B4FA;
}
scale.warm highlight {
    background-color: #E5C07B;
}
scale slider {
    min-width: 14px;
    min-height: 14px;
    margin: -3px 0;
    border-radius: 7px;
    background-color: #F3F6FC;
    border: 1px solid #363F54;
}
button.pill-btn {
    background-image: none;
    background-color: #232836;
    color: #D8DEE9;
    border: 1px solid #363F54;
    border-radius: 8px;
    padding: 4px 10px;
    box-shadow: none;
}
button.pill-btn:hover {
    background-color: #363F54;
    color: #F3F6FC;
}
button.pill-btn.active {
    background-color: #363F54;
    border-color: #89B4FA;
    color: #89B4FA;
}
button.pill-btn.muted {
    border-color: #F38BA8;
    color: #F38BA8;
}
.section-label {
    color: #8E95A8;
    font-size: 8.5pt;
}
"""


def kill_existing(requested_mode: str) -> bool:
    """Kill existing popup; return True only if the same mode was already open."""
    if not os.path.exists(PID_FILE):
        return False
    same_mode = False
    try:
        with open(PID_FILE) as f:
            raw = f.read().strip()
        old_mode, old_pid_str = (raw.split(":", 1) + [""])[:2] if ":" in raw else ("", raw)
        old_pid = int(old_pid_str)
        if old_pid != os.getpid():
            os.kill(old_pid, signal.SIGTERM)
            same_mode = old_mode == requested_mode
    except Exception:
        pass
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    return same_mode


def get_brightness_pct() -> int:
    try:
        out = subprocess.check_output(["xrandr", "--verbose"], text=True, stderr=subprocess.DEVNULL)
        m = re.search(r"Brightness:\s*([0-9.]+)", out)
        if m:
            return max(10, min(100, round(float(m.group(1)) * 100)))
    except Exception:
        pass
    return 100


def set_brightness_pct(pct: int):
    val = max(0.10, min(1.0, pct / 100.0))
    subprocess.Popen(
        ["xrandr", "--output", MONITOR, "--brightness", f"{val:.2f}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def is_night_mode() -> bool:
    return subprocess.run(["pgrep", "-x", "gammastep"], stdout=subprocess.DEVNULL).returncode == 0


def toggle_night_mode():
    if is_night_mode():
        subprocess.run(["killall", "-q", "gammastep"], check=False)
    else:
        subprocess.Popen(
            ["gammastep", "-m", "randr", "-O", "3000"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def get_audio_state() -> tuple[int, bool]:
    pct = 50
    muted = False
    try:
        v_out = subprocess.check_output(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"], text=True, stderr=subprocess.DEVNULL
        )
        m = re.search(r"(\d+)%", v_out)
        if m:
            pct = max(0, min(100, int(m.group(1))))
        m_out = subprocess.check_output(
            ["pactl", "get-sink-mute", "@DEFAULT_SINK@"], text=True, stderr=subprocess.DEVNULL
        )
        muted = "yes" in m_out.lower()
    except Exception:
        pass
    return pct, muted


def get_sinks() -> tuple[str, list[tuple[str, str]]]:
    default_sink = ""
    sinks = []
    try:
        default_sink = subprocess.check_output(
            ["pactl", "get-default-sink"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        raw = subprocess.check_output(["pactl", "list", "sinks"], text=True, stderr=subprocess.DEVNULL)
        cur_name = None
        for line in raw.splitlines():
            line_s = line.strip()
            if line_s.startswith("Name:"):
                cur_name = line_s.split(":", 1)[1].strip()
            elif line_s.startswith("Description:") and cur_name:
                desc = line_s.split(":", 1)[1].strip()
                if len(desc) > 28:
                    desc = desc[:27] + "…"
                sinks.append((cur_name, desc))
                cur_name = None
    except Exception:
        pass
    return default_sink, sinks


def switch_sink(sink_name: str):
    subprocess.run(["pactl", "set-default-sink", sink_name], check=False)
    try:
        inputs = subprocess.check_output(
            ["pactl", "list", "short", "sink-inputs"], text=True, stderr=subprocess.DEVNULL
        )
        for line in inputs.splitlines():
            parts = line.split()
            if parts:
                subprocess.run(["pactl", "move-sink-input", parts[0], sink_name], check=False)
    except Exception:
        pass


class ControlPopup(Gtk.Window):
    def __init__(self, mode: str):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.mode = mode
        self.created_at = time.monotonic()
        self.last_apply = 0.0
        self.pending_timer = None

        self.set_name("polybar-control")
        self.set_title("polybar-control")
        self.set_role("polybar-control")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_default_size(POPUP_WIDTH, -1)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None and screen.is_composited():
            self.set_visual(visual)
        self.set_app_paintable(True)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.connect("key-press-event", self.on_key)
        self.connect("focus-out-event", self.on_focus_out)
        self.connect("destroy", self.on_destroy)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(14)
        box.set_margin_end(14)
        self.add(box)

        if mode == "brightness":
            self.build_brightness(box)
        else:
            self.build_audio(box)

        self.position_near_pointer(screen)
        self.show_all()

    def position_near_pointer(self, screen):
        display = Gdk.Display.get_default()
        seat = display.get_default_seat()
        pointer = seat.get_pointer()
        _, px, _ = pointer.get_position()
        mon = display.get_monitor_at_point(px, 20)
        geom = mon.get_geometry()
        x = max(geom.x + 16, min(px - POPUP_WIDTH // 2, geom.x + geom.width - POPUP_WIDTH - 24))
        y = geom.y + 42
        self.move(x, y)

    def on_key(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.close()

    def on_focus_out(self, _widget, _event):
        if time.monotonic() - self.created_at > 0.25:
            self.close()

    def on_destroy(self, _widget):
        try:
            if os.path.exists(PID_FILE):
                with open(PID_FILE) as f:
                    if f.read().strip().endswith(f":{os.getpid()}"):
                        os.remove(PID_FILE)
        except Exception:
            pass
        Gtk.main_quit()

    def build_brightness(self, box):
        pct = get_brightness_pct()

        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(label="Brightness")
        title.get_style_context().add_class("header-title")
        title.set_halign(Gtk.Align.START)
        self.val_lbl = Gtk.Label(label=f"{pct}%")
        self.val_lbl.get_style_context().add_class("header-value")
        self.val_lbl.set_halign(Gtk.Align.END)
        hdr.pack_start(title, True, True, 0)
        hdr.pack_end(self.val_lbl, False, False, 0)
        box.pack_start(hdr, False, False, 0)

        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 10, 100, 5)
        scale.get_style_context().add_class("warm")
        scale.set_draw_value(False)
        scale.set_value(pct)
        scale.connect("value-changed", self.on_brightness_changed)
        box.pack_start(scale, False, False, 0)

        presets = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        presets.set_homogeneous(True)
        for p in (30, 60, 80, 100):
            btn = Gtk.Button(label=f"{p}%")
            btn.get_style_context().add_class("pill-btn")
            btn.connect("clicked", lambda _b, val=p, sc=scale: sc.set_value(val))
            presets.pack_start(btn, True, True, 0)
        box.pack_start(presets, False, False, 0)

        self.night_btn = Gtk.Button()
        self.night_btn.get_style_context().add_class("pill-btn")
        self.update_night_btn()
        self.night_btn.connect("clicked", self.on_night_clicked)
        box.pack_start(self.night_btn, False, False, 0)

    def update_night_btn(self):
        active = is_night_mode()
        ctx = self.night_btn.get_style_context()
        if active:
            self.night_btn.set_label("Night Mode (3000K): On")
            ctx.add_class("active")
        else:
            self.night_btn.set_label("Night Mode (3000K): Off")
            ctx.remove_class("active")

    def on_night_clicked(self, _btn):
        toggle_night_mode()
        GLib.timeout_add(150, lambda: (self.update_night_btn(), False)[1])

    def on_brightness_changed(self, scale):
        val = int(round(scale.get_value()))
        self.val_lbl.set_text(f"{val}%")
        if self.pending_timer:
            GLib.source_remove(self.pending_timer)
        self.pending_timer = GLib.timeout_add(30, lambda v=val: (set_brightness_pct(v), False)[1])

    def build_audio(self, box):
        pct, muted = get_audio_state()

        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(label="Audio Volume")
        title.get_style_context().add_class("header-title")
        title.set_halign(Gtk.Align.START)
        self.val_lbl = Gtk.Label(label="Muted" if muted else f"{pct}%")
        self.val_lbl.get_style_context().add_class("header-value")
        self.val_lbl.set_halign(Gtk.Align.END)
        hdr.pack_start(title, True, True, 0)
        hdr.pack_end(self.val_lbl, False, False, 0)
        box.pack_start(hdr, False, False, 0)

        self.audio_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 2)
        self.audio_scale.set_draw_value(False)
        self.audio_scale.set_value(pct)
        self.audio_scale.connect("value-changed", self.on_volume_changed)
        box.pack_start(self.audio_scale, False, False, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        actions.set_homogeneous(True)
        self.mute_btn = Gtk.Button()
        self.mute_btn.get_style_context().add_class("pill-btn")
        self.update_mute_btn(muted, pct)
        self.mute_btn.connect("clicked", self.on_mute_clicked)

        mixer_btn = Gtk.Button(label="Mixer")
        mixer_btn.get_style_context().add_class("pill-btn")
        mixer_btn.connect("clicked", self.on_mixer_clicked)

        actions.pack_start(self.mute_btn, True, True, 0)
        actions.pack_start(mixer_btn, True, True, 0)
        box.pack_start(actions, False, False, 0)

        default_sink, sinks = get_sinks()
        if sinks:
            lbl = Gtk.Label(label="Output Device")
            lbl.get_style_context().add_class("section-label")
            lbl.set_halign(Gtk.Align.START)
            box.pack_start(lbl, False, False, 0)

            self.sink_buttons = []
            for name, desc in sinks:
                btn = Gtk.Button(label=desc)
                btn.get_style_context().add_class("pill-btn")
                if name == default_sink:
                    btn.get_style_context().add_class("active")
                btn.connect("clicked", self.on_sink_clicked, name)
                self.sink_buttons.append((name, btn))
                box.pack_start(btn, False, False, 0)

    def update_mute_btn(self, muted: bool, pct: int):
        ctx = self.mute_btn.get_style_context()
        if muted:
            self.mute_btn.set_label("Unmute")
            ctx.add_class("muted")
            self.val_lbl.set_text("Muted")
        else:
            self.mute_btn.set_label("Mute")
            ctx.remove_class("muted")
            self.val_lbl.set_text(f"{pct}%")

    def on_volume_changed(self, scale):
        val = int(round(scale.get_value()))
        self.val_lbl.set_text(f"{val}%")
        now = time.monotonic()
        if now - self.last_apply > 0.03:
            self.last_apply = now
            subprocess.Popen(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{val}%"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            if self.pending_timer:
                GLib.source_remove(self.pending_timer)
            self.pending_timer = GLib.timeout_add(
                40,
                lambda v=val: (
                    subprocess.Popen(
                        ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{v}%"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    ),
                    False,
                )[1],
            )

    def on_mute_clicked(self, _btn):
        subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"], check=False)
        pct, muted = get_audio_state()
        self.update_mute_btn(muted, pct)

    def on_mixer_clicked(self, _btn):
        subprocess.Popen(["pavucontrol"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        self.close()

    def on_sink_clicked(self, _btn, sink_name: str):
        switch_sink(sink_name)
        for name, b in self.sink_buttons:
            ctx = b.get_style_context()
            if name == sink_name:
                ctx.add_class("active")
            else:
                ctx.remove_class("active")
        pct, muted = get_audio_state()
        self.audio_scale.set_value(pct)
        self.update_mute_btn(muted, pct)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "audio"
    if kill_existing(mode):
        return

    with open(PID_FILE, "w") as f:
        f.write(f"{mode}:{os.getpid()}")

    ControlPopup(mode)
    Gtk.main()


if __name__ == "__main__":
    main()
