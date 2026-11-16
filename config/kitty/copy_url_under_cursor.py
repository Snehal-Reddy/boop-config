#!/usr/bin/env python3
"""Kitty kitten: copy URL/hyperlink under cursor (or via selection/hints fallback)."""

from __future__ import annotations

from kittens.tui.handler import result_handler
from kitty.clipboard import set_clipboard_string
from kitty.fast_data_types import click_mouse_url


def main(args: list[str]) -> str:
    return ""


def _copy_hovered_url(window) -> bool:
    """Copy the hyperlink or URL under the mouse cursor if present."""
    copied = False
    prev_handler = window.open_url_handler

    def grab_url(_boss, _win, url: str, _hyperlink_id: int, _cwd: str) -> bool:
        nonlocal copied
        if url:
            set_clipboard_string(url)
            copied = True
        return True

    window.open_url_handler = grab_url
    try:
        click_mouse_url(window.os_window_id, window.tab_id, window.id)
    finally:
        window.open_url_handler = prev_handler
    return copied


@result_handler(no_ui=True)
def handle_result(args: list[str], answer: str, target_window_id: int, boss) -> None:
    window = boss.window_id_map.get(target_window_id)
    if window is None:
        return

    no_hints = "--no-hints" in args[1:]

    if not no_hints and window.screen.has_selection():
        window.copy_to_clipboard()
        return

    if _copy_hovered_url(window):
        boss.handle_clipboard_loss("clipboard")
        return

    if no_hints:
        return

    hint_type = "hyperlink" if window.screen.hyperlinks_as_set() else "url"
    boss.run_kitten_with_metadata(
        "hints",
        (f"--type={hint_type}", "--program=@"),
        window=window,
    )
