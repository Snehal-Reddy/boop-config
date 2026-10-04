#!/usr/bin/env python3
"""Patch leaf binary so Ctrl+Q quits leaf alongside q (matching micro's Ctrl+Q habit)."""

import os
import re
import shutil
import struct
import sys


def patch_leaf(path: str) -> None:
    if not os.path.isfile(path):
        print(f"skip: leaf binary not found at {path}")
        return

    with open(path, "rb") as f:
        data = bytearray(f.read())

    # Pattern in leaf::runtime::run for 'q' (0x71):
    #   f6 44 24 ?? 02          testb $0x2, disp8(%rsp)
    #   0f 84 <rel32>           je <quit_label>
    #   48 8d bc 24             lea disp32(%rsp), %rdi
    already_pat = re.compile(rb"\xf6\x44\x24.\x02\xe9....\x90\x48\x8d\xbc\x24", re.DOTALL)
    if already_pat.search(data):
        print(f"ok: {path} already patched for Ctrl+Q quit")
        return

    pat = re.compile(rb"\xf6\x44\x24.\x02\x0f\x84(....)\x48\x8d\xbc\x24", re.DOTALL)
    matches = list(pat.finditer(data))
    if len(matches) != 1:
        print(f"skip: expected 1 match in {path}, found {len(matches)}")
        return

    m = matches[0]
    rel32 = struct.unpack("<i", m.group(1))[0]
    # Converting 6-byte `0f 84 <rel32>` (next RIP = pos + 6) to 5-byte `e9 <new_rel32>` + `90` (next RIP = pos + 5)
    new_rel32 = rel32 + 1
    jmp_bytes = b"\xe9" + struct.unpack("<4s", struct.pack("<i", new_rel32))[0] + b"\x90"

    bak = path + ".bak"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)

    je_offset = m.start() + 5
    data[je_offset : je_offset + 6] = jmp_bytes

    # Also update the built-in '?' help popup label if present
    help_old = b"path viewerq           t          toggle toc"
    help_new = b"path viewerctrl+q, q   t          toggle toc"
    if help_old in data:
        data = data.replace(help_old, help_new, 1)

    with open(path, "wb") as f:
        f.write(data)
    print(f"patched {path} (Ctrl+Q and q now both quit leaf; backup at {bak})")


if __name__ == "__main__":
    target = (
        sys.argv[1]
        if len(sys.argv) > 1
        else (shutil.which("leaf") or os.path.expanduser("~/.local/bin/leaf"))
    )
    patch_leaf(target)
