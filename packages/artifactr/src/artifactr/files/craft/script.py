"""An app with no server: a script its CLI runs, for one call, given the call as JSON.

Each call writes the call, and the source if there is one, into an empty temporary directory,
starts the CLI there on the adapter's script, and reads back the result the script wrote beside
the call, and the files it wrote in `out/`; the process and the directory end with the call
(native files ADR-0014). It is the one place a script CLI is started, as
[`Spawn`][artifactr.files.craft.Spawn] is for an MCP server, with the same deadline, launcher
and failures.
"""

import contextlib
import json
import os
import signal
import subprocess
import tempfile
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TextIO

import anyio
from pydantic import BaseModel, JsonValue, ValidationError

from artifactr.files.app import AppFailed
from artifactr.files.craft.registry import Craft

SOURCE: Final = "document"
"""The source's name in `in/`, before its extension: the same for every call."""

ENVIRONMENT: Final = {"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin", "QT_QPA_PLATFORM": "offscreen"}
"""All the CLI is given of an environment, but its `HOME`, which is the call's directory."""

KEPT: Final = 4000
"""The most characters of what the CLI printed that a crash's message keeps: its start and end.

Blender prints its own lines first and the cause of its end last, such as a library it couldn't
load before it rendered (#783): a tail alone, or a head alone, can miss either.
"""


class _Result(BaseModel):
    version: str
    result: JsonValue = None
    refused: str | None = None


@dataclass(frozen=True)
class Ran:
    """What a call's script returned: its result, and the files wanted that it wrote, by name."""

    result: JsonValue
    files: Mapping[str, bytes]


class Script:
    """Starts an app's CLI on a script, once for each call, given the call as JSON.

    The CLI runs as this process's user, with nothing of its environment but the locale, and its
    home in the call's directory. An app whose script confines nothing (its descriptor's `roots`
    is `none`) reads and writes wherever that user can, so it is started only when the operator
    says the files are trusted, or that this process is already confined, as the worker is.

    Args:
        craft: The app.
        cli: Its CLI.
        script: The script the CLI runs, given `--pass` and the call's path.
        version: The version it must be, which the script reports: another is refused.
        arguments: What the CLI is given before the script.
        ending: What it is given after the script, before `--pass`: Blender's `--`, after which
            it leaves its arguments to the script.
        trusted: Whether the files are trusted, or this process confined: required of an app
            that confines nothing.
        limit: The most bytes a file it writes may hold.
        launcher: The command the CLI is started under, given the CLI and its arguments.

    Raises:
        ValueError: If the app confines nothing and `trusted` isn't given.
    """

    def __init__(
        self,
        craft: Craft,
        cli: str | Path,
        script: Path,
        *,
        version: str,
        arguments: Sequence[str] = (),
        ending: Sequence[str] = (),
        trusted: bool = False,
        limit: int,
        launcher: Sequence[str] = (),
    ) -> None:
        if craft.roots == "none" and not trusted:
            raise ValueError(
                f"{craft.cli} confines no file its script reads or writes: run it only on "
                "trusted files, or in the worker, with trusted=True"
            )
        self.craft = craft
        self.version = version
        self._command = (*launcher, str(cli), *arguments, str(script), *ending)
        self._limit = limit

    async def run(
        self,
        deadline: float,
        call: Mapping[str, JsonValue],
        source: bytes | None,
        extension: str,
        *,
        wanted: Collection[str] = (),
    ) -> Ran:
        """Run the script on the call, and the source, in a directory of the call's own.

        Of the files the script writes in `out/`, only those `wanted` are read back.

        Raises:
            AppFailed: `timeout` past the deadline; `crashed` if the script wrote no result that
                parses; `refused` if the script refused, or ran on another version; `too_large`
                if a file it wrote is past the limit.
        """
        cli = self.craft.cli
        with tempfile.TemporaryDirectory(prefix=f"{self.craft.name}-") as directory:
            root = Path(directory)
            (root / "in").mkdir()
            (root / "out").mkdir()
            if source is not None:
                (root / "in" / f"{SOURCE}{extension}").write_bytes(source)
            (root / "call.json").write_text(json.dumps(call))
            with (root / "printed").open("w+", errors="replace") as printed:
                try:
                    with anyio.fail_after(deadline):
                        status = await self._process(root, printed.fileno())
                except TimeoutError:
                    raise AppFailed("timeout", f"{cli} took more than {deadline:.3g}s") from None
                try:
                    ran = _Result.model_validate_json((root / "result.json").read_bytes())
                except (OSError, ValidationError):
                    # A script that ended before writing its result: how it ended, and what it
                    # printed, say why.
                    raise AppFailed(
                        "crashed",
                        f"{cli} wrote no result, and ended with {_ended(status)}; "
                        f"it printed: {_printed(printed)}",
                    ) from None
            if ran.version != self.version:
                raise AppFailed("refused", f"{cli} is {ran.version}, not {self.version}")
            if ran.refused is not None:
                raise AppFailed("refused", ran.refused)
            return Ran(ran.result, self._written(root / "out", wanted))

    async def _process(self, root: Path, printed: int) -> int:
        """The CLI's exit status, run to its end, or killed with the call when its deadline passes.

        It runs in a session of its own, and whatever of its group is left when the call ends,
        however it ends, is killed with it: nothing it started outlives the call in its group.
        """
        process = await anyio.open_process(
            [*self._command, "--pass", str(root / "call.json")],
            cwd=root,
            env={**ENVIRONMENT, "HOME": str(root)},
            stdin=subprocess.DEVNULL,
            stdout=printed,
            stderr=printed,
            start_new_session=True,
        )
        try:
            return await process.wait()
        finally:
            # The group is gone already, or only its leader is left, unreaped.
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(process.pid, signal.SIGKILL)
            with anyio.CancelScope(shield=True):
                await process.wait()

    def _written(self, out: Path, wanted: Collection[str]) -> dict[str, bytes]:
        """Each file wanted that the script wrote, refused as too large past the limit."""
        written: dict[str, bytes] = {}
        for path in sorted(out.iterdir()):
            if path.name not in wanted:
                continue
            if path.stat().st_size > self._limit:
                raise AppFailed("too_large", f"{path.name} is larger than {self._limit} bytes")
            written[path.name] = path.read_bytes()
        return written


def _ended(status: int) -> str:
    """How the CLI ended, by its exit status: negative, the signal that killed it."""
    if status < 0:
        return f"signal {-status} ({signal.Signals(-status).name})"
    return f"exit status {status}"


def _printed(printed: TextIO) -> str:
    """What the CLI printed, whole up to KEPT characters, or its start and its end past it."""
    size = printed.seek(0, 2)
    printed.seek(0)
    if size <= KEPT:
        return printed.read().strip()
    head = printed.read(KEPT // 4)
    printed.seek(size - (KEPT - KEPT // 4))
    tail = printed.read()
    return f"{head.strip()}\n[...]\n{tail.strip()}"
