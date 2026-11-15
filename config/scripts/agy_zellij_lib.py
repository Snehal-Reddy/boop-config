#!/usr/bin/env python3
"""Shared helpers for tracking and resurrecting agy CLI conversations in Zellij panes."""

from __future__ import annotations

import contextlib
import fcntl
import glob
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from typing import Any

HOME = os.path.expanduser("~")
UID = os.getuid()

ZELLIJ_BIN = shutil.which("zellij") or os.path.join(HOME, ".cargo", "bin", "zellij")
AGY_BIN = os.path.join(HOME, ".local", "bin", "agy")
AGY_RESURRECT_BIN = os.path.join(HOME, ".local", "bin", "agy-resurrect")

STATE_DIR = os.path.join(
    os.environ.get("XDG_STATE_HOME") or os.path.join(HOME, ".local", "state"),
    "agy-zellij",
    "sessions",
)
PRESENCE_DIR = os.path.join(HOME, ".gemini", "antigravity-cli", "presence")
CONVERSATIONS_DIR = os.path.join(HOME, ".gemini", "antigravity-cli", "conversations")
ZELLIJ_CACHE_INFO_DIR = os.path.join(
    os.environ.get("XDG_CACHE_HOME") or os.path.join(HOME, ".cache"),
    "zellij",
    "contract_version_1",
    "session_info",
)

SAFE_CONV_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
STARTUP_GRACE_SECS = 5.0
RESURRECT_CLEAR_GRACE_SECS = 2.0
DUMMY_MATCH_PENALTY = 100_000_000


def get_zellij_socket_base() -> str:
    """Return Zellij's contract_version_1 socket directory without creating it."""
    sock_dir = os.environ.get("ZELLIJ_SOCKET_DIR")
    if sock_dir:
        nested = os.path.join(sock_dir, "contract_version_1")
        if os.path.isdir(nested):
            return nested
        return sock_dir
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{UID}"
    candidate = os.path.join(runtime_dir, "zellij", "contract_version_1")
    if os.path.isdir(candidate):
        return candidate
    fallback = os.path.join(f"/tmp/zellij-{UID}", "contract_version_1")
    if os.path.isdir(fallback):
        return fallback
    return candidate


def session_state_paths(session_name: str) -> tuple[str, str]:
    """Return sanitized (state_json_path, lock_path) for a Zellij session."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", session_name).strip("._-") or "session"
    digest = hashlib.sha256(session_name.encode("utf-8")).hexdigest()[:8]
    stem = f"{slug[:64]}-{digest}"
    return (
        os.path.join(STATE_DIR, f"{stem}.json"),
        os.path.join(STATE_DIR, f"{stem}.lock"),
    )


@contextlib.contextmanager
def session_lock(session_name: str):
    """Acquire an exclusive flock around a session's state file."""
    os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
    _, lock_path = session_state_paths(session_name)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def read_state(json_path: str, session_name: str) -> dict[str, Any]:
    """Load persisted session state or return an empty v1 structure."""
    default: dict[str, Any] = {
        "version": 1,
        "session_name": session_name,
        "server_id": None,
        "resurrected_at": 0.0,
        "active": {},
        "pending_pool": [],
    }
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return default
        data.setdefault("version", 1)
        data.setdefault("session_name", session_name)
        data.setdefault("server_id", None)
        data.setdefault("resurrected_at", 0.0)
        if not isinstance(data.get("active"), dict):
            data["active"] = {}
        if not isinstance(data.get("pending_pool"), list):
            data["pending_pool"] = []
        # Normalize pane_id keys to str.
        data["active"] = {str(k): v for k, v in data["active"].items() if isinstance(v, dict)}
        return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def atomic_write_state(json_path: str, data: dict[str, Any]) -> None:
    """Atomically write session state with 0600 permissions."""
    os.makedirs(os.path.dirname(json_path), mode=0o700, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=os.path.dirname(json_path))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp_path, json_path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def get_server_id(session_name: str) -> str | None:
    """Return a unique incarnation token for a live Zellij session socket."""
    sock_path = os.path.join(get_zellij_socket_base(), session_name)
    try:
        st = os.stat(sock_path)
    except OSError:
        return None
    if not stat.S_ISSOCK(st.st_mode):
        return None
    return f"{st.st_ino}:{st.st_ctime_ns}"


def list_live_sessions() -> list[str]:
    """Return session names that currently have a live Unix socket."""
    base = get_zellij_socket_base()
    try:
        names = os.listdir(base)
    except OSError:
        return []
    live: list[str] = []
    for name in sorted(names):
        try:
            st = os.stat(os.path.join(base, name))
            if stat.S_ISSOCK(st.st_mode):
                live.append(name)
        except OSError:
            continue
    return live


def list_panes(session_name: str, timeout: float = 2.0) -> list[dict[str, Any]] | None:
    """Query Zellij for all panes in a live session; return None on failure/timeout."""
    env = os.environ.copy()
    for key in ("ZELLIJ", "ZELLIJ_SESSION_NAME", "ZELLIJ_PANE_ID"):
        env.pop(key, None)
    try:
        res = subprocess.run(
            [ZELLIJ_BIN, "--session", session_name, "action", "list-panes", "--all", "--json"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if res.returncode != 0 or not res.stdout.strip():
        return None
    try:
        panes = json.loads(res.stdout)
        return panes if isinstance(panes, list) else None
    except json.JSONDecodeError:
        return None


def compute_tab_dims(panes: list[dict[str, Any]]) -> dict[int, tuple[int, int]]:
    """Derive (tab_width, tab_height) per tab_position from list-panes geometry."""
    tiled_bounds: dict[int, tuple[int, int]] = {}
    all_bounds: dict[int, tuple[int, int]] = {}
    for p in panes:
        if p.get("is_plugin"):
            continue
        tab_pos = int(p.get("tab_position", 0))
        x2 = int(p.get("pane_x", 0)) + max(int(p.get("pane_columns", 0)), 1)
        y2 = int(p.get("pane_y", 0)) + max(int(p.get("pane_rows", 0)), 1)
        pw, ph = all_bounds.get(tab_pos, (1, 1))
        all_bounds[tab_pos] = (max(pw, x2), max(ph, y2))
        if not p.get("is_floating"):
            tw, th = tiled_bounds.get(tab_pos, (1, 1))
            tiled_bounds[tab_pos] = (max(tw, x2), max(th, y2))
    return {tab: tiled_bounds.get(tab, dims) for tab, dims in all_bounds.items()}


def normalize_pane_geo(
    pane: dict[str, Any], tab_dims: dict[int, tuple[int, int]]
) -> tuple[int, bool, float, float]:
    """Return (tab_position, is_floating, cx, cy) normalized to [0, 1]."""
    tab_pos = int(pane.get("tab_position", 0))
    is_floating = bool(pane.get("is_floating", False))
    tw, th = tab_dims.get(tab_pos, (1, 1))
    cx = (float(pane.get("pane_x", 0)) + float(pane.get("pane_columns", 0)) / 2.0) / max(tw, 1)
    cy = (float(pane.get("pane_y", 0)) + float(pane.get("pane_rows", 0)) / 2.0) / max(th, 1)
    return tab_pos, is_floating, cx, cy


def read_proc_locks() -> dict[tuple[int, int, int], list[int]]:
    """Parse /proc/locks into {(major, minor, inode): [pid, ...]} without acquiring locks."""
    locks: dict[tuple[int, int, int], list[int]] = {}
    try:
        with open("/proc/locks", "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return locks

    for line in lines:
        parts = line.split()
        if len(parts) < 8:
            continue
        # Blocked waiters format as "123: -> FLOCK ..." and shift columns; skip them.
        if parts[1] == "->":
            continue
        lock_kind = parts[1]
        if lock_kind not in ("FLOCK", "POSIX", "OFDLCK"):
            continue
        try:
            pid = int(parts[4])
            dev_ino = parts[5].split(":")
            if len(dev_ino) != 3:
                continue
            maj = int(dev_ino[0], 16)
            minor = int(dev_ino[1], 16)
            ino = int(dev_ino[2], 10)
        except ValueError:
            continue
        if pid <= 0:
            continue
        locks.setdefault((maj, minor, ino), []).append(pid)
    return locks


def conv_db_exists(conv_id: str | None) -> bool:
    """Return True if conv_id is well-formed and has a persisted conversation .db."""
    if not conv_id or not SAFE_CONV_RE.match(conv_id):
        return False
    return os.path.isfile(os.path.join(CONVERSATIONS_DIR, f"{conv_id}.db"))


def get_presence_locks() -> dict[str, list[int]]:
    """Return {conv_id: [pid, ...]} for all held agy presence/*.lock files."""
    if not os.path.isdir(PRESENCE_DIR):
        return {}
    proc_locks = read_proc_locks()
    if not proc_locks:
        return {}

    held: dict[str, list[int]] = {}
    try:
        entries = list(os.scandir(PRESENCE_DIR))
    except OSError:
        return {}

    for entry in entries:
        if not entry.name.endswith(".lock"):
            continue
        conv_id = entry.name[:-5]
        if not SAFE_CONV_RE.match(conv_id):
            continue
        try:
            st = entry.stat()
        except OSError:
            continue
        key = (os.major(st.st_dev), os.minor(st.st_dev), st.st_ino)
        pids = proc_locks.get(key)
        if pids:
            held[conv_id] = list(pids)
    return held


def _is_agy_proc(pid_dir: str, agy_realpath: str) -> bool:
    """Return True if /proc/<pid> is the agy CLI binary."""
    try:
        with open(os.path.join(pid_dir, "comm"), "rb") as f:
            comm = f.read().decode("utf-8", errors="ignore").strip()
        if comm == "agy":
            return True
    except OSError:
        pass
    try:
        exe = os.readlink(os.path.join(pid_dir, "exe"))
        exe_clean = exe[:-10] if exe.endswith(" (deleted)") else exe
        return os.path.realpath(exe_clean) == agy_realpath
    except OSError:
        return False


def _read_proc_env(pid_dir: str) -> dict[str, str]:
    """Read selected Zellij env vars from /proc/<pid>/environ."""
    env: dict[str, str] = {}
    try:
        with open(os.path.join(pid_dir, "environ"), "rb") as f:
            raw = f.read()
    except OSError:
        return env
    for item in raw.split(b"\0"):
        if not item:
            continue
        if item.startswith((b"ZELLIJ_SESSION_NAME=", b"ZELLIJ_PANE_ID=", b"PWD=")):
            k, _, v = item.partition(b"=")
            env[k.decode("utf-8", errors="ignore")] = v.decode("utf-8", errors="ignore")
    return env


def get_live_agy_panes() -> dict[tuple[str, str], dict[str, Any]]:
    """Return {(session_name, str(pane_id)): {pid, conv_id, cwd}} for live agy processes."""
    agy_realpath = os.path.realpath(AGY_BIN)
    presence_locks = get_presence_locks()
    pid_to_conv: dict[int, str] = {}
    for conv_id, pids in presence_locks.items():
        if not conv_db_exists(conv_id):
            continue
        for pid in pids:
            pid_to_conv[pid] = conv_id

    result: dict[tuple[str, str], dict[str, Any]] = {}
    for pid_dir in glob.glob("/proc/[0-9]*"):
        try:
            if os.stat(pid_dir).st_uid != UID:
                continue
            if not _is_agy_proc(pid_dir, agy_realpath):
                continue
            pid = int(os.path.basename(pid_dir))
            env = _read_proc_env(pid_dir)
            session_name = env.get("ZELLIJ_SESSION_NAME")
            pane_id = env.get("ZELLIJ_PANE_ID")
            if not session_name or pane_id is None or pane_id == "":
                continue
            pane_id = str(pane_id)
            try:
                cwd = os.readlink(os.path.join(pid_dir, "cwd"))
            except OSError:
                cwd = env.get("PWD")
            conv_id = pid_to_conv.get(pid)
            key = (session_name, pane_id)
            prev = result.get(key)
            # Prefer a process that holds a persisted conversation lock (higher PID tie-break).
            if prev is None or (conv_id and not prev.get("conv_id")) or (
                bool(conv_id) == bool(prev.get("conv_id")) and pid > prev["pid"]
            ):
                result[key] = {"pid": pid, "conv_id": conv_id, "cwd": cwd}
        except (OSError, ValueError):
            continue
    return result


def pid_is_alive(pid: int) -> bool:
    """Return True if pid exists and is not a zombie."""
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8", errors="ignore") as f:
            stat_line = f.read()
        rparen = stat_line.rfind(")")
        if rparen != -1:
            state_char = stat_line[rparen + 2 : rparen + 3]
            if state_char == "Z":
                return False
        return True
    except OSError:
        return False


def cmd_first_basename(cmd: str | None) -> str:
    """Return basename of the first whitespace-separated token of cmd, or ''."""
    if not cmd:
        return ""
    parts = cmd.strip().split()
    return os.path.basename(parts[0]) if parts else ""


def is_resurrect_pane(pane: dict[str, Any]) -> bool:
    """Return True if pane's terminal_command invokes agy-resurrect."""
    if pane.get("is_plugin"):
        return False
    return cmd_first_basename(pane.get("terminal_command")) == "agy-resurrect"


def is_dropped_bash_pane(pane: dict[str, Any]) -> bool:
    """Return True if pane is running an interactive shell (post-exit drop or normal bash)."""
    pc = (pane.get("pane_command") or "").strip()
    if not pc:
        return False
    parts = pc.split()
    base = os.path.basename(parts[0])
    return base in ("bash", "sh", "zsh", "fish") and "--norc" not in parts and "agy" not in pc


def is_waiting_resurrect_pane(pane: dict[str, Any]) -> bool:
    """Return True if pane is a resurrected agy-resurrect pane still suspended or starting agy."""
    if not is_resurrect_pane(pane) or pane.get("exited"):
        return False
    pc = (pane.get("pane_command") or "").strip()
    if not pc:
        # Suspended (start_suspended true) or mid-exec before proc cmdline updates.
        return True
    parts = pc.split()
    if os.path.basename(parts[0]) == "bash" and "--norc" in parts and "agy-resurrect-shell" in parts:
        return True
    return any(os.path.basename(tok) in ("agy-resurrect", "agy") for tok in parts[:2])


def reconcile_server_incarnation(state: dict[str, Any], server_id: str) -> bool:
    """Move active entries to pending_pool when Zellij server_id changes."""
    if state.get("server_id") == server_id:
        return False
    by_conv: dict[str, dict[str, Any]] = {}
    for item in state.get("pending_pool", []):
        if isinstance(item, dict) and item.get("conversation_id"):
            by_conv[item["conversation_id"]] = item
    for item in state.get("active", {}).values():
        if isinstance(item, dict) and item.get("conversation_id"):
            cid = item["conversation_id"]
            prev = by_conv.get(cid)
            if prev is None or float(item.get("updated_at", 0)) >= float(prev.get("updated_at", 0)):
                by_conv[cid] = {
                    "pane_id": str(item.get("pane_id", "")),
                    "conversation_id": cid,
                    "cwd": item.get("cwd"),
                    "tab_position": int(item.get("tab_position", 0)),
                    "is_floating": bool(item.get("is_floating", False)),
                    "cx": float(item.get("cx", 0.0)),
                    "cy": float(item.get("cy", 0.0)),
                    "updated_at": float(item.get("updated_at", 0.0)),
                }
    state["pending_pool"] = list(by_conv.values())
    state["active"] = {}
    state["server_id"] = server_id
    state["resurrected_at"] = time.time()
    return True


def hungarian_min_cost(cost_matrix: list[list[int]]) -> list[int]:
    """Solve square/rectangular min-cost assignment; return col index assigned to each row."""
    n = len(cost_matrix)
    if n == 0:
        return []
    m = len(cost_matrix[0])
    # Classic 1-indexed Jonker-Volgenant/Hungarian O(n*m^2) for n <= m.
    u = [0] * (n + 1)
    v = [0] * (m + 1)
    p = [0] * (m + 1)
    way = [0] * (m + 1)
    inf = 10**18
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [inf] * (m + 1)
        used = [False] * (m + 1)
        row_i = cost_matrix[i - 1]
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = inf
            j1 = 0
            row_i0 = cost_matrix[i0 - 1]
            for j in range(1, m + 1):
                if not used[j]:
                    cur = row_i0[j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    ans = [-1] * n
    for j in range(1, m + 1):
        if p[j] != 0:
            ans[p[j] - 1] = j - 1
    return ans


def sync_session(
    session_name: str,
    live_agy: dict[tuple[str, str], dict[str, Any]],
) -> None:
    """Reconcile and persist agy pane mappings for one live Zellij session."""
    server_id = get_server_id(session_name)
    if not server_id:
        return
    panes = list_panes(session_name, timeout=2.0)
    if panes is None:
        # Never prune on IPC failure/timeout (e.g., server shutting down).
        return

    json_path, _ = session_state_paths(session_name)
    now = time.time()

    with session_lock(session_name):
        state = read_state(json_path, session_name)
        reconcile_server_incarnation(state, server_id)

        pane_by_id = {str(p["id"]): p for p in panes if not p.get("is_plugin")}
        tab_dims = compute_tab_dims(panes)
        prev_active: dict[str, dict[str, Any]] = state.get("active", {})
        new_active: dict[str, dict[str, Any]] = {}

        # 1. Record all panes that currently have a live agy process in /proc.
        for (sess, pid_str), info in live_agy.items():
            if sess != session_name or pid_str not in pane_by_id:
                continue
            pane = pane_by_id[pid_str]
            tab_pos, is_float, cx, cy = normalize_pane_geo(pane, tab_dims)
            prev = prev_active.get(pid_str, {})
            conv_id = info.get("conv_id")
            if not conv_id:
                # During initial launch of `agy --conversation <id>`, the lock may take
                # a fraction of a second to appear in /proc/locks.
                claimed_at = float(prev.get("claimed_at", 0.0))
                if (
                    prev.get("conversation_id")
                    and claimed_at > 0.0
                    and (now - claimed_at) < STARTUP_GRACE_SECS
                    and not is_dropped_bash_pane(pane)
                ):
                    conv_id = prev["conversation_id"]
                else:
                    continue

            new_active[pid_str] = {
                "pane_id": pid_str,
                "conversation_id": conv_id,
                "cwd": pane.get("pane_cwd") or info.get("cwd") or prev.get("cwd"),
                "tab_position": tab_pos,
                "is_floating": is_float,
                "cx": cx,
                "cy": cy,
                "claimed_at": float(prev.get("claimed_at") or now),
                "updated_at": now,
            }

        # 2. Retain newly claimed agy-resurrect panes only during their brief startup grace window.
        for pid_str, prev in prev_active.items():
            if pid_str in new_active:
                continue
            pane = pane_by_id.get(pid_str)
            if pane is None or is_dropped_bash_pane(pane):
                continue
            claimed_at = float(prev.get("claimed_at", 0.0))
            if (
                is_waiting_resurrect_pane(pane)
                and claimed_at > 0.0
                and (now - claimed_at) < STARTUP_GRACE_SECS
            ):
                new_active[pid_str] = prev

        # 3. Remove any conversation already active from pending_pool.
        active_convs = {
            e["conversation_id"]
            for e in new_active.values()
            if e.get("conversation_id")
        }
        state["pending_pool"] = [
            e
            for e in state.get("pending_pool", [])
            if isinstance(e, dict)
            and e.get("conversation_id")
            and e["conversation_id"] not in active_convs
        ]

        # 4. Clear leftover pending_pool once resurrection has settled and no unclaimed
        #    non-exited agy-resurrect panes (suspended or starting) remain.
        unclaimed_resurrect = [
            pid_str
            for pid_str, pane in pane_by_id.items()
            if is_waiting_resurrect_pane(pane)
            and pid_str not in new_active
        ]
        resurrected_at = float(state.get("resurrected_at", 0.0))
        if (
            not unclaimed_resurrect
            and len(pane_by_id) > 0
            and (now - resurrected_at) >= RESURRECT_CLEAR_GRACE_SECS
        ):
            state["pending_pool"] = []

        state["active"] = new_active
        atomic_write_state(json_path, state)


def sync_all() -> None:
    """Sync all currently running Zellij sessions."""
    live_sessions = list_live_sessions()
    if not live_sessions:
        return
    live_agy = get_live_agy_panes()
    for session_name in live_sessions:
        sync_session(session_name, live_agy)
