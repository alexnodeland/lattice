"""The agent's tools for native files, which ask `NativeFiles` for everything they do.

The toolset is offered only while the app's integration is on in the run's workspace, read once
a step, so a model in a workspace where it is off never sees it; `NativeFiles` refuses there
too, whatever calls it. A rejection is raised as it is, for artifactr's capability to turn into
a retry, except a person's check-out: the agent is told who has the file and plans again after
the check-in, rather than retrying at once.
"""

import json
from collections.abc import Sequence
from typing import Annotated, Any, Final

from pydantic import Field, JsonValue
from pydantic_ai import (
    AbstractToolset,
    BinaryContent,
    FunctionToolset,
    ModelRetry,
    RunContext,
    ToolDefinition,
)

from artifactr.agent import Session, describe_outcome
from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.native import NativeFiles
from artifactr.workspace import ArtifactBusy

TEXT_CHARS: Final = 8_000
"""The most of a file's words one `read_native` returns."""

REVIEW_ITEMS: Final = 50
"""The most comments and tracked changes one `read_review` returns."""

CHECKOUT: Final = "checkout:"
"""How a person's check-out's lease holder starts: `checkout:<id>:<participant>`."""

Start = Annotated[int, Field(ge=0)]


def native_file_tools(files: NativeFiles, *, view: bool = False) -> AbstractToolset[Session[Any]]:
    """Build the toolset for native files, through `files` and its app.

    Args:
        files: The native files, and the app that reads and edits them.
        view: Whether to offer `view_page`, which shows the model one rendered page: off by
            default, since a page is an image's worth of tokens.
    """
    toolset = FunctionToolset[Session[Any]]()

    @toolset.tool
    async def read_native(ctx: RunContext[Session[Any]], artifact_id: str, start: Start = 0) -> str:
        """Read a native file's words, as plain text, 8,000 characters at a time.

        Args:
            artifact_id: The native file to read.
            start: The character to start from, to read on past the first 8,000.
        """
        text = (await files.read(ctx.deps.workspace, artifact_id, part="text")).decode()
        end = start + TEXT_CHARS
        rest = len(text) - end
        more = f"\n\n[{rest} more characters: read on from start={end}]" if rest > 0 else ""
        return text[start:end] + more

    @toolset.tool
    async def read_review(ctx: RunContext[Session[Any]], artifact_id: str, start: Start = 0) -> str:
        """Read a native file's comments and tracked changes, 50 at a time, as the app gives them.

        Args:
            artifact_id: The native file to read.
            start: The item to start from, to read on past the first 50.
        """
        review = json.loads(await files.read(ctx.deps.workspace, artifact_id, part="review"))
        items = _items(review)
        if not items:
            return "It has no comments or tracked changes."
        end = start + REVIEW_ITEMS
        shown = "\n".join(json.dumps(item, ensure_ascii=False) for item in items[start:end])
        rest = len(items) - end
        return shown + (f"\n\n[{rest} more: read on from start={end}]" if rest > 0 else "")

    @toolset.tool_plain
    async def find_commands(query: str) -> str:
        """Find the app's commands that edit a native file, ten at most, by a word they mention.

        Args:
            query: A word in the command's name or description, such as "comment" or "table".
        """
        found = await files.app.commands(query)
        if not found:
            return f"No command mentions {query!r}: try another word."
        return "\n".join(f"- {c.signature}: {c.description}" for c in found)

    @toolset.tool
    async def edit_native(
        ctx: RunContext[Session[Any]],
        artifact_id: str,
        base_version: int,
        commands: list[AppCommand],
        summary: str,
    ) -> str:
        """Edit a native file by a batch of its app's commands, run in order on its head.

        Find the commands with `find_commands` first. The batch stops at the first command that
        fails, which changes nothing.

        Args:
            artifact_id: The native file to edit.
            base_version: The version you read, which must still be the head's.
            commands: Each command's name, and its arguments by name.
            summary: A short description of the change, shown to others.
        """
        try:
            outcome = await files.edit(
                ctx.deps.workspace,
                artifact_id,
                base_version=base_version,
                commands=commands,
                summary=summary,
                thread_id=ctx.deps.thread_id,
            )
        except ArtifactBusy as busy:
            lease = busy.lease
            if lease is None or not lease.holder.startswith(CHECKOUT):
                raise  # free again, or another edit's for seconds: the capability retries
            who = lease.holder.split(":", 2)[2]
            return (
                f"{artifact_id} is checked out by {who} until {lease.expires_at.isoformat()}. "
                "Don't edit it now: plan again once it is checked in, from its version then."
            )
        except AppFailed as failed:
            if failed.failure != "refused":
                raise
            raise ModelRetry(f"The app refused the batch: {failed}") from failed
        if outcome is None:
            return "The batch changed nothing in the file."
        return describe_outcome(outcome)

    if view:

        @toolset.tool
        async def view_page(
            ctx: RunContext[Session[Any]], artifact_id: str, page: Annotated[int, Field(ge=1)] = 1
        ) -> BinaryContent:
            """Look at one page of a native file's head, rendered as the app shows it.

            Args:
                artifact_id: The native file to look at.
                page: The page, from 1.
            """
            try:
                png = await files.render(ctx.deps.workspace, artifact_id, page)
            except AppFailed as failed:
                if failed.failure != "refused":
                    raise
                raise ModelRetry(f"The app can't show that page: {failed}") from failed
            return BinaryContent(data=png, media_type="image/png")

    async def offered(
        ctx: RunContext[Session[Any]], tools: list[ToolDefinition]
    ) -> list[ToolDefinition]:
        return tools if await files.enabled(ctx.deps.workspace) else []

    return toolset.prepared(offered)


def _items(review: dict[str, JsonValue]) -> Sequence[JsonValue]:
    """A review's comments, then its tracked changes, each marked with which it is."""
    items: list[JsonValue] = []
    for kind, label in (("comments", "comment"), ("changes", "change")):
        found = review.get(kind)
        items.extend(
            {**item, "kind": label} if isinstance(item, dict) else {"kind": label, "text": item}
            for item in (found if isinstance(found, list) else [])
        )
    return items
