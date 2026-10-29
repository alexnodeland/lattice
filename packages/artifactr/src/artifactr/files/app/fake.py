"""An app that stands in for a native one in tests: its files are JSON, and it is instant.

A file holds paragraphs and comments, and the number of times it was saved, which every save
stamps, as a native app stamps the time: so the bytes change on every save, and the fingerprint
only when the paragraphs or comments do.
"""

import hashlib
import json
import math
from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel, JsonValue, ValidationError

from artifactr.files.app.png import solid
from artifactr.files.app.port import (
    AppCommand,
    AppFailed,
    Applied,
    CommandSpec,
    Failure,
    Inspection,
    Talk,
)
from artifactr.files.manifest import OUTLINE_LIMIT

PAGE: Final = 3
"""How many paragraphs a page of a fake file holds."""

COMMANDS: Final = (
    CommandSpec(
        name="add_paragraph", signature="add_paragraph(text)", description="Append a paragraph."
    ),
    CommandSpec(
        name="replace_paragraph",
        signature="replace_paragraph(index, text)",
        description="Replace the paragraph at an index, from 0.",
    ),
    CommandSpec(
        name="delete_paragraph",
        signature="delete_paragraph(index)",
        description="Delete the paragraph at an index, from 0.",
    ),
    CommandSpec(name="add_comment", signature="add_comment(text)", description="Add a comment."),
)


class _File(BaseModel):
    paragraphs: list[str] = []
    comments: list[str] = []
    saves: int = 0


class FakeApp:
    """A fake [`App`][artifactr.files.app.App], for tests: it reads and writes its own JSON files.

    Args:
        fails: How every call fails, to test what happens when the app does; None for never.
        integration: The key that switches it, if not its class's, `files:fake`: another, to
            stand in for one of several apps.
    """

    name: str = "fake"
    version: str = "1.0"
    build: str | None = None
    talk: Talk = "save"
    integration: str = "files:fake"

    def __init__(self, *, fails: Failure | None = None, integration: str | None = None) -> None:
        self.fails: Failure | None = fails
        if integration is not None:
            self.integration = integration

    @staticmethod
    def file(*paragraphs: str, comments: Sequence[str] = ()) -> bytes:
        """Make a file, as an upload would bring it."""
        return (
            _File(paragraphs=list(paragraphs), comments=list(comments)).model_dump_json().encode()
        )

    async def apply(
        self, source: bytes | None, commands: Sequence[AppCommand], *, deadline: float
    ) -> Applied:
        """Apply a batch of commands; refuse the batch if any command doesn't apply."""
        del deadline  # the fake is instant
        self._maybe_fail()
        file = _File() if source is None else _read(source)
        for command in commands:
            _run(file, command)
        file.saves += 1
        content = file.model_dump_json().encode()
        return Applied(content=content, inspection=_inspect(file))

    async def inspect(self, source: bytes, *, deadline: float) -> Inspection:
        """Read a file's fingerprint, outline, text, review and pages."""
        del deadline
        self._maybe_fail()
        return _inspect(_read(source))

    async def render(self, source: bytes, page: int, *, scale: float, deadline: float) -> bytes:
        """Render a page as a one-pixel PNG whose colour comes from the page's paragraphs."""
        del deadline
        self._maybe_fail()
        file = _read(source)
        pages = _pages(file)
        if not 1 <= page <= pages:
            raise AppFailed("refused", f"page {page} is not in a file of {pages}")
        shown = file.paragraphs[(page - 1) * PAGE : page * PAGE]
        return solid(1, 1, hashlib.sha256(json.dumps([shown, scale]).encode()).digest()[:3])

    async def commands(self, query: str) -> Sequence[CommandSpec]:
        """Find the commands whose name or description mentions the query."""
        found = [c for c in COMMANDS if query.lower() in f"{c.name} {c.description}".lower()]
        return found[:10]

    def _maybe_fail(self) -> None:
        if self.fails is not None:
            raise AppFailed(self.fails, "the fake app was told to fail")


def _read(source: bytes) -> _File:
    try:
        return _File.model_validate_json(source)
    except ValidationError:
        raise AppFailed("refused", "not a file of the fake app") from None


def _run(file: _File, command: AppCommand) -> None:
    args = command.args
    match command.name, args:
        case "add_paragraph", {"text": str(text)}:
            file.paragraphs.append(text)
        case "replace_paragraph", {"index": int(index), "text": str(text)} if _has(file, index):
            file.paragraphs[index] = text
        case "delete_paragraph", {"index": int(index)} if _has(file, index):
            del file.paragraphs[index]
        case "add_comment", {"text": str(text)}:
            file.comments.append(text)
        case _:
            raise AppFailed("refused", f"{command.name} doesn't apply with {args}")


def _has(file: _File, index: int) -> bool:
    return 0 <= index < len(file.paragraphs)


def _inspect(file: _File) -> Inspection:
    kept: JsonValue = {"paragraphs": list(file.paragraphs), "comments": list(file.comments)}
    canonical = json.dumps(kept, sort_keys=True, separators=(",", ":"))
    outline = "\n".join(p.splitlines()[0] for p in file.paragraphs if p)
    return Inspection(
        fingerprint=hashlib.sha256(canonical.encode()).hexdigest(),
        outline=outline[:OUTLINE_LIMIT],
        text="\n\n".join(file.paragraphs),
        review={"comments": [{"id": i, "text": c} for i, c in enumerate(file.comments)]},
        pages=_pages(file),
    )


def _pages(file: _File) -> int:
    """A file's pages: one at least, as an empty document has."""
    return max(1, math.ceil(len(file.paragraphs) / PAGE))
