"""What the worker clears after each call, where it is alone in its container: a stray's chance.

A CLI the worker starts runs in a session of its own, and its group is killed with its call. A
hostile file that runs code in the CLI can still start a process in a session of its own, which
outlives the call, as the worker's own user, and sees every later call: of any tenant. So, where
the worker is the only thing its user runs, as in its image, each call ends with every other
process of its user killed, and the temporary directory, where each call's files are, emptied.
"""

import contextlib
import os
import shutil
import signal
import tempfile
from collections.abc import Callable
from pathlib import Path

PROC = Path("/proc")


def sweep(
    *,
    proc: Path = PROC,
    temporary: Path | None = None,
    kill: Callable[[int, int], None] = os.kill,
) -> list[int]:
    """Kill every process of this user but this one and its ancestors, and empty `temporary`.

    Args:
        proc: Where the processes are listed: Linux's `/proc`.
        temporary: The directory each call's files are in; the system's by default.
        kill: How a process is killed; `os.kill`, but in tests.

    Returns:
        The processes killed.
    """
    kept = _ancestors(proc, os.getpid())
    user = os.getuid()
    killed: list[int] = []
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) in kept:
            continue
        with contextlib.suppress(OSError):
            if entry.stat().st_uid == user:
                kill(int(entry.name), signal.SIGKILL)
                killed.append(int(entry.name))
    for left in Path(temporary or tempfile.gettempdir()).iterdir():
        if left.is_dir() and not left.is_symlink():
            shutil.rmtree(left, ignore_errors=True)
        else:
            left.unlink(missing_ok=True)
    return killed


def _ancestors(proc: Path, pid: int) -> set[int]:
    """The process and each of its parents, up to the first."""
    chain: set[int] = set()
    while pid > 0 and pid not in chain:
        chain.add(pid)
        try:
            # The parent is the fourth field, after the name, which is in parentheses.
            pid = int((proc / str(pid) / "stat").read_text().rpartition(")")[2].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return chain
