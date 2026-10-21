"""What the worker clears after each call, where it is alone in its container: a stray's chance.

A CLI the worker starts runs in a session of its own, and its group is killed with its call. A
hostile file that runs code in the CLI can still start a process in a session of its own, which
outlives the call, as the worker's own user, and sees every later call: of any tenant. So, where
the worker is the only thing its user runs, as in its image, each call ends with every other
process of its user killed, and the temporary directory, where each call's files are, emptied.
"""

import contextlib
import os
import signal
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Final

PROC = Path("/proc")


PASSES: Final = 10
"""How many times the processes are listed, at most, until a listing finds none to kill: strays
that start each other again as they are killed are killed again, or the sweep fails."""


class SweepFailed(RuntimeError):
    """The sweep left something behind: the worker must take no other call."""


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

    Raises:
        SweepFailed: If processes were still starting after `PASSES` listings, or anything is
            left in `temporary`.
    """
    kept = _ancestors(proc, os.getpid())
    user = os.getuid()
    killed: list[int] = []
    for _ in range(PASSES):
        found = [pid for pid in _users(proc, user) if pid not in kept and pid not in killed]
        if not found:
            break
        for pid in found:
            with contextlib.suppress(OSError):
                kill(pid, signal.SIGKILL)
            killed.append(pid)
    else:
        raise SweepFailed(f"processes were still starting after {PASSES} sweeps")
    directory = Path(temporary or tempfile.gettempdir())
    for left in directory.iterdir():
        _remove(left)
    if remaining := sorted(left.name for left in directory.iterdir()):
        raise SweepFailed(f"{directory} still holds {', '.join(remaining)}")
    return killed


def _users(proc: Path, user: int) -> list[int]:
    """The processes of this user, as `proc` lists them now."""
    found: list[int] = []
    for entry in proc.iterdir():
        with contextlib.suppress(OSError):
            if entry.name.isdigit() and entry.stat().st_uid == user:
                found.append(int(entry.name))
    return found


def _remove(path: Path) -> None:
    """Remove a file, or a directory and all it holds, whatever its mode: its owner may."""
    if path.is_symlink() or not path.is_dir():
        with contextlib.suppress(OSError):
            path.unlink()
        return
    with contextlib.suppress(OSError):
        path.chmod(stat.S_IRWXU)
    with contextlib.suppress(OSError):
        for child in path.iterdir():
            _remove(child)
    with contextlib.suppress(OSError):
        path.rmdir()


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
