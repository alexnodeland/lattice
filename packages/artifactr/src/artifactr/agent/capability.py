"""The ArtifactWorkspace capability: artifactr's integration with pydantic-ai (ADR-0006).

Add it to an agent whose ``deps_type`` is :class:`~artifactr.agent.Session`. It contributes
the generic artifact tools and instructions, and its hooks make every run a participant in the
workspace: runs and tool calls are recorded, what others did is told to the agent, and messages
sent during a run steer it.
"""

import asyncio
import contextlib
import json
from collections.abc import Sequence
from dataclasses import KW_ONLY, dataclass, field
from typing import Any, override

from pydantic_ai import (
    AgentRunResult,
    DeferredToolRequests,
    FunctionToolset,
    ModelRetry,
    RunContext,
    ToolCallPart,
    ToolDefinition,
)
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.capabilities.abstract import (
    ValidatedToolArgs,
    WrapRunHandler,
    WrapToolExecuteHandler,
)
from pydantic_ai.exceptions import ToolFailedError, ToolRetryError

from artifactr.agent.session import Session, last_seen
from artifactr.agent.tools import artifact_tools
from artifactr.core import (
    Artifact,
    ArtifactId,
    DeferredRequest,
    FocusChanged,
    MessagePosted,
    Note,
    Rejection,
    RunEnded,
    RunPaused,
    RunStarted,
    RunUsage,
    ToolCalled,
    ToolReturned,
    VersionConflict,
    change_notes,
    render_notes,
    same_participant,
)

type Context = RunContext[Session[Any]]

INTRO = (
    "You collaborate with the people in this thread through shared artifacts. People and "
    "other agents can change them at any time: you are told what changed as it happens, "
    "inside <workspace-changes> tags. Read an artifact before changing it, and prefer small, "
    "precise edits."
)
SUGGEST = "This thread is in suggest mode: your changes are recorded as proposals for review."


@dataclass
class ArtifactWorkspace(AbstractCapability[Session[Any]]):
    """Make an agent a participant in a workspace.

    Args:
        types: The artifact types the agent may create.
        ask: Include the ``ask_user`` tool, which pauses the run until someone answers. The
            agent's ``output_type`` must then include ``DeferredToolRequests``.
        max_render_chars: How much of each followed artifact's rendering to include in the
            instructions.
        max_summary_chars: How much of each tool call's arguments and result to record.
    """

    types: Sequence[type[Artifact]]
    _: KW_ONLY
    ask: bool = False
    max_render_chars: int = 4000
    max_summary_chars: int = 200
    _toolset: FunctionToolset[Session[Any]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._toolset = artifact_tools(self.types, ask=self.ask)

    @override
    def get_toolset(self) -> FunctionToolset[Session[Any]]:
        """Return the generic artifact tools."""
        return self._toolset

    @override
    def get_instructions(self) -> Any:
        """Return the instructions, rendered fresh for every model request."""
        return self._instructions

    async def _instructions(self, ctx: Context) -> str:
        workspace = ctx.deps.workspace
        thread = await workspace.thread(ctx.deps.thread_id)
        sections = [INTRO]
        if thread.mode == "suggest":
            sections.append(SUGGEST)
        sections.append(
            f"Kinds of artifact you can create: {', '.join(t.kind for t in self.types)}."
        )
        followed = [await workspace.artifact(artifact_id) for artifact_id in thread.focus]
        if followed:
            rendered = "\n\n".join(
                f'<artifact id="{a.id}" kind="{a.kind}" version="{a.version}"'
                f"{' archived' if a.archived else ''}>\n"
                f"{_clip(a.data.render_for_agent(), self.max_render_chars)}\n</artifact>"
                for a in followed
            )
            sections.append(f"The artifacts you follow, as they are now:\n\n{rendered}")
        mine = [
            p
            for p in await workspace.proposals()
            if same_participant(p.proposed_by, workspace.actor)
        ]
        if mine:
            listed = ", ".join(f"{p.id} (for {p.artifact_id})" for p in mine)
            sections.append(f"Your proposals awaiting review: {listed}.")
        return "\n\n".join(sections)

    # ─── the run ──────────────────────────────────────────────────────────────

    @override
    async def wrap_run(self, ctx: Context, *, handler: WrapRunHandler) -> AgentRunResult[Any]:
        """Record the run, brief the agent, and watch the workspace while it runs."""
        session = ctx.deps
        workspace = session.workspace
        started = await workspace.record(
            RunStarted(run_id=session.run_id, thread_id=session.thread_id, trigger=session.trigger)
        )
        watch_after = started.seq if session.watch_after is None else session.watch_after
        thread = await workspace.thread(session.thread_id)
        since = await last_seen(workspace, session.thread_id)
        missed = [e for e in await workspace.read(after_seq=since) if e.seq <= (watch_after or 0)]
        notes = change_notes(missed, viewer=workspace.actor, focus=thread.focus)
        if notes:
            ctx.enqueue(_wrap(notes))
        watcher = asyncio.create_task(self._watch(ctx, watch_after or 0, set(thread.focus)))
        try:
            result = await handler()
        except asyncio.CancelledError:
            await workspace.record(self._ended(session, "stopped"))
            raise
        except Exception as error:
            await workspace.record(self._ended(session, "failed", error=str(error)))
            raise
        finally:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher
        await self._finish(session, result)
        return result

    async def _watch(self, ctx: Context, after_seq: int, focus: set[ArtifactId]) -> None:
        workspace = ctx.deps.workspace
        thread_id = ctx.deps.thread_id
        async for envelope in workspace.subscribe(after_seq=after_seq, threads={thread_id}):
            event = envelope.event
            if isinstance(event, FocusChanged) and event.thread_id == thread_id:
                focus = set(event.artifact_ids)
            elif same_participant(envelope.actor, workspace.actor):
                continue
            elif isinstance(event, MessagePosted) and event.thread_id == thread_id:
                ctx.enqueue(event.content)
            elif notes := change_notes([envelope], viewer=workspace.actor, focus=focus):
                ctx.enqueue(_wrap(notes))

    async def _finish(self, session: Session[Any], result: AgentRunResult[Any]) -> None:
        workspace = session.workspace
        history = result.new_messages_json()
        output = result.output
        if isinstance(output, DeferredToolRequests):
            requests = (
                *_requests(output.calls, "question"),
                *_requests(output.approvals, "approval"),
            )
            paused = RunPaused(
                run_id=session.run_id, thread_id=session.thread_id, requests=requests
            )
            await workspace.record(paused, history=history)
            return
        if isinstance(output, str) and output.strip():
            await workspace.post_message(session.thread_id, output)
        usage = RunUsage(
            requests=result.usage.requests,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
        )
        await workspace.record(self._ended(session, "completed", usage=usage), history=history)

    @staticmethod
    def _ended(
        session: Session[Any],
        status: Any,
        *,
        usage: RunUsage | None = None,
        error: str | None = None,
    ) -> RunEnded:
        return RunEnded(
            run_id=session.run_id,
            thread_id=session.thread_id,
            status=status,
            usage=usage,
            error=error,
        )

    # ─── tool calls ───────────────────────────────────────────────────────────

    @override
    async def before_tool_execute(
        self, ctx: Context, *, call: ToolCallPart, tool_def: ToolDefinition, args: ValidatedToolArgs
    ) -> ValidatedToolArgs:
        """Record the tool call."""
        summary = _clip(json.dumps(args, default=str), self.max_summary_chars)
        await ctx.deps.workspace.record(self._tool_called(ctx, call, summary))
        return args

    @override
    async def wrap_tool_execute(
        self,
        ctx: Context,
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: ValidatedToolArgs,
        handler: WrapToolExecuteHandler,
    ) -> Any:
        """Record a tool's own ``ModelRetry`` or ``ToolFailed``, which skip the error hook."""
        try:
            return await handler(args)
        except (ToolRetryError, ToolFailedError) as error:
            status = "retry" if isinstance(error, ToolRetryError) else "error"
            summary = _clip(str(error), self.max_summary_chars)
            await ctx.deps.workspace.record(self._tool_returned(ctx, call, status, summary))
            raise

    @override
    async def after_tool_execute(
        self,
        ctx: Context,
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: ValidatedToolArgs,
        result: Any,
    ) -> Any:
        """Record the tool's result."""
        summary = _clip(str(result), self.max_summary_chars)
        await ctx.deps.workspace.record(self._tool_returned(ctx, call, "ok", summary))
        return result

    @override
    async def on_tool_execute_error(
        self,
        ctx: Context,
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: ValidatedToolArgs,
        error: Exception,
    ) -> Any:
        """Turn rejections into retries the model can act on; record every failure."""
        workspace = ctx.deps.workspace
        if isinstance(error, Rejection):
            await workspace.record(self._tool_returned(ctx, call, "retry", error.message))
            hint = (
                " Read the artifact again, then retry."
                if isinstance(error, VersionConflict)
                else ""
            )
            raise ModelRetry(error.message + hint) from error
        summary = _clip(f"{type(error).__name__}: {error}", self.max_summary_chars)
        await workspace.record(self._tool_returned(ctx, call, "error", summary))
        raise error

    @staticmethod
    def _tool_called(ctx: Context, call: ToolCallPart, summary: str) -> ToolCalled:
        return ToolCalled(
            run_id=ctx.deps.run_id,
            thread_id=ctx.deps.thread_id,
            tool_call_id=call.tool_call_id,
            tool_name=call.tool_name,
            args_summary=summary,
        )

    @staticmethod
    def _tool_returned(ctx: Context, call: ToolCallPart, status: Any, summary: str) -> ToolReturned:
        return ToolReturned(
            run_id=ctx.deps.run_id,
            thread_id=ctx.deps.thread_id,
            tool_call_id=call.tool_call_id,
            status=status,
            summary=summary,
        )


def _requests(calls: list[ToolCallPart], kind: Any) -> list[DeferredRequest]:
    return [
        DeferredRequest(
            tool_call_id=call.tool_call_id,
            tool_name=call.tool_name,
            kind=kind,
            args=call.args_as_dict(),
        )
        for call in calls
    ]


def _wrap(notes: list[Note]) -> str:
    return f"<workspace-changes>\n{render_notes(notes)}\n</workspace-changes>"


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
