#!/usr/bin/env python3
"""Patch leaf binary so Ctrl+Q quits leaf alongside q (matching micro's Ctrl+Q habit)."""

import os
import re
import shutil
import stat
import struct
import sys
import tempfile


def patch_leaf(path: str) -> None:
    if not os.path.isfile(path):
        print(f"skip: leaf binary not found at {path}")
        return

    with open(path, "rb") as f:
        data = bytearray(f.read())

    if data[:4] != b"\x7fELF":
        print(f"skip: {path} is not a Linux ELF binary")
        return

    changed = False
    notes: list[str] = []

    # 1. Patch leaf::runtime::run for 'q' (0x71) so Ctrl+Q also quits leaf:
    #   f6 44 24 ?? 02          testb $0x2, disp8(%rsp)
    #   0f 84 <rel32>           je <quit_label>
    #   48 8d bc 24             lea disp32(%rsp), %rdi
    already_pat = re.compile(rb"\xf6\x44\x24.\x02\xe9....\x90\x48\x8d\xbc\x24", re.DOTALL)
    if already_pat.search(data):
        notes.append("Ctrl+Q quit already patched")
    else:
        pat = re.compile(rb"\xf6\x44\x24.\x02\x0f\x84(....)\x48\x8d\xbc\x24", re.DOTALL)
        matches = list(pat.finditer(data))
        if len(matches) != 1:
            print(f"skip Ctrl+Q: expected 1 match in {path}, found {len(matches)}")
        else:
            m = matches[0]
            rel32 = struct.unpack("<i", m.group(1))[0]
            # Converting 6-byte `0f 84 <rel32>` (next RIP = pos + 6) to 5-byte `e9 <new_rel32>` + `90` (next RIP = pos + 5)
            new_rel32 = rel32 + 1
            jmp_bytes = b"\xe9" + struct.unpack("<4s", struct.pack("<i", new_rel32))[0] + b"\x90"

            je_offset = m.start() + 5
            data[je_offset : je_offset + 6] = jmp_bytes

            help_old = b"path viewerq           t          toggle toc"
            help_new = b"path viewerctrl+q, q   t          toggle toc"
            if help_old in data:
                data = data.replace(help_old, help_new, 1)
            changed = True
            notes.append("patched Ctrl+Q quit")

    # 2. Prevent leaf from seeing KITTY_PID and trying `kitty @ launch --type=tab`
    #    on Ctrl+E; instead suspend leaf, run micro inline, and resume leaf on quit.
    kitty_marker = b"leaf editor: KITTY_PIDGNOME_TERMINAL_SCREEN"
    kitty_patched = b"leaf editor: KITTY_XIDGNOME_TERMINAL_SCREEN"
    if kitty_patched in data:
        notes.append("inline Ctrl+E already patched")
    elif data.count(kitty_marker) == 1:
        data = data.replace(kitty_marker, kitty_patched, 1)
        changed = True
        notes.append("patched inline Ctrl+E (disabled Kitty tab spawn)")
    else:
        print(f"skip inline Ctrl+E: marker not unique in {path}")

    if not changed:
        print(f"ok: {path} ({', '.join(notes)})")
        return

    bak = path + ".bak"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)

    st_mode = stat.S_IMODE(os.stat(path).st_mode)
    parent = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(prefix=".patch-leaf-", dir=parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp_path, st_mode)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    print(f"updated {path}: {', '.join(notes)} (backup at {bak})")


if __name__ == "__main__":
    target = (
        sys.argv[1]
        if len(sys.argv) > 1
        else (shutil.which("leaf") or os.path.expanduser("~/.local/bin/leaf"))
    )
    patch_leaf(target)
