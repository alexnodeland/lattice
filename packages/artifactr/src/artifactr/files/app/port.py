"""The app port: a native application, called statelessly, bytes in and bytes out.

Each call takes the file's bytes and returns new bytes or what was read from them, so no
document stays open between calls. One adapter per app, since apps' control channels and
commands differ; [`FakeApp`][artifactr.files.app.FakeApp] stands in for one in tests.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from artifactr.files.manifest import OUTLINE_LIMIT, Sha256

Failure = Literal["timeout", "crashed", "too_large", "refused"]
"""How a call can fail: past its deadline, the app crashed, a limit was breached, or the app
refused the file or a command."""


class AppFailed(Exception):
    """A call to the app failed, in one of the ways [`Failure`][artifactr.files.app.Failure] names.

    Attributes:
        failure: How it failed.
    """

    def __init__(self, failure: Failure, message: str) -> None:
        super().__init__(f"{failure}: {message}")
        self.failure: Failure = failure


class AppCommand(BaseModel):
    """One of an app's own commands, as an agent asks for it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    args: dict[str, JsonValue] = {}


class CommandSpec(BaseModel):
    """A command an app offers: its name, how it is called, and what it does."""

    model_config = ConfigDict(frozen=True)

    name: str
    signature: str
    description: str


class Inspection(BaseModel):
    """What an app reads from a file."""

    model_config = ConfigDict(frozen=True)

    fingerprint: Sha256
    """The digest of the content, normalized: what each save stamps left out."""

    outline: str = Field(default="", max_length=OUTLINE_LIMIT)
    text: str = ""
    review: dict[str, JsonValue] = {}
    """Its comments and tracked changes."""

    pages: int | None = Field(default=None, ge=0)


@dataclass(frozen=True)
class Applied:
    """A batch of commands applied: the new bytes, and what the app read from them."""

    content: bytes
    inspection: Inspection


class App(Protocol):
    """A native application, run headless, that edits one format by its own commands.

    Every call is given a deadline, in seconds, and fails with
    [`AppFailed`][artifactr.files.app.AppFailed] when it can't finish.
    """

    @property
    def name(self) -> str:
        """The app's name, such as `wordcraft`, which provenance records."""
        ...

    @property
    def version(self) -> str:
        """The app's version, which provenance records."""
        ...

    @property
    def build(self) -> str | None:
        """The digest of the image the app runs in, if it runs in one."""
        ...

    async def apply(
        self, source: bytes | None, commands: Sequence[AppCommand], *, deadline: float
    ) -> Applied:
        """Apply a batch of commands to a file, or to a new one if `source` is None."""
        ...

    async def inspect(self, source: bytes, *, deadline: float) -> Inspection:
        """Read a file's fingerprint, outline, text, review and pages."""
        ...

    async def render(self, source: bytes, page: int, *, scale: float, deadline: float) -> bytes:
        """Render one page of a file, from 1, as a PNG."""
        ...

    async def commands(self, query: str) -> Sequence[CommandSpec]:
        """Find the commands that match a query, ten at most."""
        ...
