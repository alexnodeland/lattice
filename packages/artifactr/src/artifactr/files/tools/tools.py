"""The agent's tools for native files, which ask `NativeFiles` for everything they do.

The toolset is offered only while an app's integration is on in the run's workspace, read once
a step, so a model in a workspace where every app is off never sees it; `NativeFiles` refuses a
file whose app is off, whatever calls it. A rejection is raised as it is, for artifactr's
capability to turn into a retry, except a person's check-out: the agent is told who has the
file and plans again after the check-in, rather than retrying at once. `create_native_file`
answers every refusal in a sentence instead, since none is fixed by calling it again at once.
"""

import copy
import dataclasses
import hashlib
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

from artifactr.agent import Session, describe_outcome, follow
from artifactr.core import (
    AlreadyExists,
    ArtifactId,
    Forbidden,
    NotEnabled,
    Proposed,
    ValidationFailed,
    artifact_types,
)
from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.blobs import OverQuota, TooLarge
from artifactr.files.manifest import NativeFile
from artifactr.files.native import Busy, NativeFiles, Paced
from artifactr.telemetry import annotate, attribution, outcome_attributes
from artifactr.workspace import ArtifactBusy, Workspace

TEXT_CHARS: Final = 8_000
"""The most of a file's words one `read_native` returns."""

REVIEW_ITEMS: Final = 50
"""The most comments and tracked changes one `read_review` returns."""

CHECKOUT: Final = "checkout:"
"""How a person's check-out's lease holder starts: `checkout:<id>:<participant>`."""

CREATES_PER_RUN: Final = 10
"""How many files one run segment may create, past which `create_native_file` refuses: so a
looping or misled agent never spends the whole of its person's pace or quota."""

Start = Annotated[int, Field(ge=0)]


def native_file_tools(
    files: NativeFiles, *, view: bool = False, creates: int = CREATES_PER_RUN
) -> AbstractToolset[Session[Any]]:
    """Build the toolset for native files, through `files` and its app.

    Args:
        files: The native files, and the app that reads and edits them.
        view: Whether to offer `view_page`, which shows the model one rendered page: off by
            default, since a page is an image's worth of tokens.
        creates: How many files one run segment may create: ten by default.
    """
    toolset = FunctionToolset[Session[Any]]()

    async def creatable(ws: Workspace) -> dict[str, type[NativeFile]]:
        """The native types whose app is on in the workspace, by kind."""
        return {kind: t for kind, t in _native_types().items() if await files.enabled(ws, t)}

    async def listed(ctx: RunContext[Session[Any]], tool: ToolDefinition) -> ToolDefinition:
        """`create_native_file`, offering the types the run's workspace may create."""
        types = await creatable(ctx.deps.workspace)
        lines = "\n".join(
            f"- {kind} ({', '.join(files.extensions(t))}): {_noun(t)}" for kind, t in types.items()
        )
        schema = copy.deepcopy(tool.parameters_json_schema)
        schema["properties"]["type"]["enum"] = list(types)
        return dataclasses.replace(
            tool,
            description=f"{tool.description}\n\nThe types you may create here:\n{lines}",
            parameters_json_schema=schema,
        )

    @toolset.tool(prepare=listed)
    async def create_native_file(ctx: RunContext[Session[Any]], type: str, title: str) -> str:
        """Create an empty native file of a type, named by its title, to edit with `edit_native`.

        It is made at once, by the type's app; find its commands with `find_commands`, then
        write it with `edit_native` from version 1. You are told when others change it.

        Args:
            type: The type of file, one of those listed.
            title: The file's name, such as "Travel plan"; its extension is added.
        """
        session = ctx.deps
        ws = session.workspace
        file_type = (await creatable(ws)).get(type)
        if file_type is None:
            return f"{type!r} can't be created in this workspace: create one of the types listed."
        # The call's own id, so a call retried after it succeeded makes one file.
        artifact_id = _call_id(session.run_id, ctx.tool_call_id)
        if artifact_id not in session.made and len(session.made) >= creates:
            return f"You have created {creates} files in this run: create no more until asked."
        session.made.add(artifact_id)  # before the commit, which the run's watcher then skips
        annotate(
            attribution(
                tenant_id=ws.tenant_id,
                workspace_id=ws.workspace_id,
                thread_id=session.thread_id,
                run_id=session.run_id,
                actor=ws.actor,
            )
        )
        try:
            outcome = await files.create(
                ws, file_type, title, artifact_id=artifact_id, thread_id=session.thread_id
            )
        except (Forbidden, NotEnabled) as refused:
            return f"You may not create {_noun(file_type)} here: {refused}."
        except (Paced, Busy, OverQuota, TooLarge, ValidationFailed, AlreadyExists) as refused:
            noun = _noun(file_type)
            return f"{noun[0].upper()}{noun[1:]} wasn't created: {refused}."
        except AppFailed as failed:
            if failed.failure == "refused":
                return f"The app can't make {_noun(file_type)} from nothing: {failed}."
            return f"The app that makes {_noun(file_type)} is unavailable now: {failed}."
        if outcome is not None:  # None: made by this call before, and retried
            annotate(outcome_attributes(outcome))
        if isinstance(outcome, Proposed):
            return describe_outcome(outcome)
        await follow(ctx, artifact_id)
        head = await ws.get(NativeFile, artifact_id)
        return (
            f"Created {artifact_id}: {_noun(file_type)} named {head.data.name}, at version "
            f"{head.version}. Edit it with edit_native."
        )

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

    @toolset.tool
    async def find_commands(ctx: RunContext[Session[Any]], artifact_id: str, query: str) -> str:
        """Find the commands of a native file's app that edit it, ten at most, by a word.

        Args:
            artifact_id: The native file to edit.
            query: A word in the command's name or description, such as "comment" or "table".
        """
        head = await ctx.deps.workspace.get(NativeFile, artifact_id)
        found = await files.app_of(type(head.data)).commands(query)
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


def _call_id(run_id: str, tool_call_id: str | None) -> ArtifactId:
    """The id of the file a tool call creates: the same for the same call, retried."""
    digest = hashlib.sha256(f"{run_id}:{tool_call_id}".encode()).hexdigest()
    return f"art_{digest[:16]}"


def _native_types() -> dict[str, type[NativeFile]]:
    """Every native type registered, by kind, in order."""
    found = artifact_types()
    return {kind: t for kind in sorted(found) if issubclass(t := found[kind], NativeFile)}


def _noun(file_type: type[NativeFile]) -> str:
    """What a native type's file is called, such as `a Word document`."""
    return file_type.noun or f"a {file_type.kind.replace('_', ' ')}"


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
