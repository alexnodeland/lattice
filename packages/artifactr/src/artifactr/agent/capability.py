"""The ArtifactWorkspace capability: artifactr's integration with pydantic-ai (ADR-0006).

Add it to an agent whose ``deps_type`` is :class:`~artifactr.agent.Session`. It contributes
the generic artifact tools and instructions, and its hooks make every run a participant in the
workspace: runs and tool calls are recorded, what others did is told to the agent, and messages
sent during a run steer it, up to the first from someone the run does not act for (ADR-0057).
Notices are for people, so the agent is not told of them unless it asks (ADR-0051).

Its hooks run inside pydantic-ai's spans when the agent is instrumented: ``wrap_run`` inside
``invoke_agent`` and ``wrap_tool_execute`` inside ``execute_tool``. They add artifactr's
attribution to those spans, and record each attempt's trace id with ``run_started``.
"""

import asyncio
import json
import logging
import re
from collections.abc import Sequence
from dataclasses import KW_ONLY, dataclass, field
from typing import Any, override

from pydantic import ValidationError
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
    RawToolArgs,
    ValidatedToolArgs,
    WrapRunHandler,
    WrapToolExecuteHandler,
)
from pydantic_ai.exceptions import (
    ToolFailedError,
    ToolRetryError,
    UnexpectedModelBehavior,
    UserError,
)

from artifactr.agent.session import Session, last_seen
from artifactr.agent.tools import artifact_tools
from artifactr.core import (
    Artifact,
    ArtifactId,
    DeferredRequest,
    FocusChanged,
    InvalidState,
    MessagePosted,
    Note,
    Rejection,
    RunEnded,
    RunEvent,
    RunPaused,
    RunStarted,
    RunUsage,
    ToolCalled,
    ToolReturned,
    VersionConflict,
    change_notes,
    render_notes,
    same_participant,
    same_principal,
)
from artifactr.telemetry import annotate, attribution, current_trace_id
from artifactr.telemetry.attributes import ARTIFACT_ID
from artifactr.workspace import Workspace

type Context = RunContext[Session[Any]]

logger = logging.getLogger("artifactr.agent")


class RunFailure(Exception):
    """An exception that fails a run for a known reason, recorded in its ``run_ended``.

    Raise a subclass from a tool or a capability to give a failure a typed reason instead of an
    opaque error: the run ends as ``failed``, with ``reason`` and the exception's message.

    Args:
        message: What happened, for people.
        reason: A short, stable code, such as ``guardrail_blocked``.
    """

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


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
        max_summary_chars: How much of each tool call's arguments and result to record, which
            is what people see of the call.
        notices: Tell the agent about the notices others post in its thread, as change notes,
            when a run starts and while it runs, so they are kept in its history. They are left
            out by default.
    """

    types: Sequence[type[Artifact]]
    _: KW_ONLY
    ask: bool = False
    max_render_chars: int = 4000
    max_summary_chars: int = 2000
    notices: bool = False
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
        delivered = session.delivered
        annotate(_attribution(session))
        # The run's input, up to where its watcher starts, is taken as the run starts.
        taken = max(delivered.seq, session.watch_after or 0)
        started = await workspace.record(
            RunStarted(
                run_id=session.run_id,
                thread_id=session.thread_id,
                trigger=session.trigger,
                trace_id=current_trace_id(),
                message_ids=session.message_ids,
            ),
            cursor=delivered.at(taken),
            claim=delivered.claim,
        )
        watch_after = (started.seq if session.watch_after is None else session.watch_after) or 0
        thread = await workspace.thread(session.thread_id)
        notes = await workspace.change_notes(
            after_seq=await last_seen(workspace, session.thread_id),
            before_seq=watch_after + 1,
            focus=thread.focus,
            notices=self.notices,
        )
        if notes:
            ctx.enqueue(_wrap(notes))
        delivered.seq = max(taken, watch_after)
        watcher = asyncio.create_task(self._watch(ctx, watch_after, set(thread.focus)))
        try:
            try:
                result = await handler()
            finally:  # the watcher stops before the run's end is recorded, however it ends
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)
        except asyncio.CancelledError:
            stopped = self._ended(session, "stopped")
            await _record(workspace, stopped, cursor=delivered.at(delivered.seq))
            raise
        except Exception as error:
            reason = _reason(error)
            failed = self._ended(session, "failed", error=redacted(str(error)), reason=reason)
            await _record(workspace, failed, cursor=delivered.at(delivered.seq))
            raise
        await self._finish(session, result)
        return result

    async def _watch(self, ctx: Context, after_seq: int, focus: set[ArtifactId]) -> None:
        """Deliver what others do into the run, and note in the session how far it got.

        A turn acts for one author (ADR-0057): it stops at the first message from someone the
        run does not act for, before noting it delivered, so the thread's next turn takes it.
        """
        session = ctx.deps
        workspace = session.workspace
        try:
            async for envelope in workspace.subscribe(
                after_seq=after_seq, threads={session.thread_id}
            ):
                event = envelope.event
                if isinstance(event, FocusChanged):
                    focus = set(event.artifact_ids)
                elif same_participant(envelope.actor, workspace.actor):
                    pass
                elif isinstance(event, MessagePosted) and event.kind == "message":
                    if not same_principal(envelope.actor, workspace.actor):
                        return  # one author per turn: the next turn acts for this one's
                    ctx.enqueue(event.content)
                elif notes := change_notes(
                    [envelope], viewer=workspace.actor, focus=focus, notices=self.notices
                ):
                    ctx.enqueue(_wrap(notes))
                session.delivered.seq = envelope.seq
        except UserError:
            return  # the agent's run is over and takes nothing more: the thread's next turn will
        except Exception:
            logger.exception(
                "watching the workspace for run %s failed; the run goes on", ctx.deps.run_id
            )

    async def _finish(self, session: Session[Any], result: AgentRunResult[Any]) -> None:
        workspace = session.workspace
        taken = session.delivered.at(session.delivered.seq)
        history = result.new_messages_json()
        output = result.output
        usage = RunUsage(
            requests=result.usage.requests,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
        )
        if isinstance(output, DeferredToolRequests):
            requests = (
                *_requests(output.calls, "question"),
                *_requests(output.approvals, "approval"),
            )
            paused = RunPaused(
                run_id=session.run_id,
                thread_id=session.thread_id,
                requests=requests,
                usage=usage,
            )
            await _record(workspace, paused, history=history, cursor=taken)
            return
        if isinstance(output, str) and output.strip():
            await workspace.post_message(session.thread_id, output)
        ended = self._ended(session, "completed", usage=usage)
        await _record(workspace, ended, history=history, cursor=taken)

    @staticmethod
    def _ended(
        session: Session[Any],
        status: Any,
        *,
        usage: RunUsage | None = None,
        error: str | None = None,
        reason: str | None = None,
    ) -> RunEnded:
        return RunEnded(
            run_id=session.run_id,
            thread_id=session.thread_id,
            status=status,
            usage=usage,
            error=error,
            reason=reason,
        )

    # ─── tool calls ───────────────────────────────────────────────────────────

    @override
    async def before_tool_execute(
        self, ctx: Context, *, call: ToolCallPart, tool_def: ToolDefinition, args: ValidatedToolArgs
    ) -> ValidatedToolArgs:
        """Record the tool call."""
        called = self._tool_called(ctx, call, json.dumps(args, default=str), _named(args))
        await ctx.deps.workspace.record(called)
        return args

    @override
    async def on_tool_validate_error(
        self,
        ctx: Context,
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: RawToolArgs,
        error: ValidationError | ModelRetry,
    ) -> ValidatedToolArgs:
        """Record a call whose arguments were refused, and why: the model is told, and retries."""
        workspace = ctx.deps.workspace
        raw = args if isinstance(args, str) else json.dumps(args, default=str)
        named = None if isinstance(args, str) else _named(args)
        await workspace.record(self._tool_called(ctx, call, raw, named))
        why = redacted(str(error))
        await _record(workspace, self._tool_returned(ctx, call, "retry", why, named))
        raise error

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
        attributes = _attribution(ctx.deps)
        if isinstance(artifact_id := args.get("artifact_id"), str):
            attributes[ARTIFACT_ID] = artifact_id
        annotate(attributes)
        try:
            return await handler(args)
        except (ToolRetryError, ToolFailedError) as error:
            status = "retry" if isinstance(error, ToolRetryError) else "error"
            why = redacted(str(error))
            returned = self._tool_returned(ctx, call, status, why, _named(args))
            await _record(ctx.deps.workspace, returned)
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
        returned = self._tool_returned(ctx, call, "ok", str(result), _named(args))
        await _record(ctx.deps.workspace, returned)
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
            retry = self._tool_returned(ctx, call, "retry", error.message, _named(args))
            await _record(workspace, retry)
            hint = (
                " Read the artifact again, then retry."
                if isinstance(error, VersionConflict)
                else ""
            )
            raise ModelRetry(error.message + hint) from error
        why = redacted(f"{type(error).__name__}: {error}")
        await _record(workspace, self._tool_returned(ctx, call, "error", why, _named(args)))
        raise error

    def _tool_called(
        self, ctx: Context, call: ToolCallPart, args: str, artifact_id: str | None
    ) -> ToolCalled:
        """The call, its arguments cut to ``max_summary_chars``, and whether they were."""
        return ToolCalled(
            run_id=ctx.deps.run_id,
            thread_id=ctx.deps.thread_id,
            tool_call_id=call.tool_call_id,
            tool_name=call.tool_name,
            args_summary=_clip(args, self.max_summary_chars),
            args_truncated=len(args) > self.max_summary_chars,
            artifact_id=artifact_id,
        )

    def _tool_returned(
        self, ctx: Context, call: ToolCallPart, status: Any, said: str, artifact_id: str | None
    ) -> ToolReturned:
        """How the call returned, what it said cut to ``max_summary_chars``, and whether it was."""
        return ToolReturned(
            run_id=ctx.deps.run_id,
            thread_id=ctx.deps.thread_id,
            tool_call_id=call.tool_call_id,
            tool_name=call.tool_name,
            status=status,
            summary=_clip(said, self.max_summary_chars),
            truncated=len(said) > self.max_summary_chars,
            artifact_id=artifact_id,
        )


async def _record(
    workspace: Workspace,
    fact: RunEvent,
    *,
    history: bytes | None = None,
    cursor: tuple[str, int] | None = None,
) -> None:
    """Record how a tool call or the run ended, unless the run was abandoned meanwhile.

    Once a run's claim lapsed, the thread's next claim records it as failed, abandoned, and core
    refuses what the run records afterwards as ``invalid_state``. Such an end, of a tool already
    running or of the run, is dropped and logged, as reflexr drops an abandoned attempt's
    outcome. A tool call is recorded without this, so its refusal fails the run before the tool
    runs.
    """
    try:
        await workspace.record(fact, history=history, cursor=cursor)
    except InvalidState as refused:
        if (await workspace.run(fact.run_id)).status != "failed":
            raise
        logger.info("the %s of a run that has failed is dropped: %s", fact.type, refused.message)


def _attribution(session: Session[Any]) -> dict[str, Any]:
    workspace = session.workspace
    return attribution(
        tenant_id=workspace.tenant_id,
        workspace_id=workspace.workspace_id,
        thread_id=session.thread_id,
        run_id=session.run_id,
        actor=workspace.actor,
        user=session.on_behalf_of,
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


def _named(args: dict[str, Any]) -> str | None:
    """The artifact a call's arguments name, by the ``artifact_id`` artifactr's tools take."""
    artifact_id = args.get("artifact_id")
    return artifact_id if isinstance(artifact_id, str) else None


_SECRETS = (
    # A URL's credentials and query, where tokens and keys travel; its host and path stay.
    (re.compile(r"(\w+://)[^/\s@]*@"), r"\1"),
    (re.compile(r"(\w+://[^\s?#]*)[?#][^\s'\"]*"), r"\1"),
    # An Authorization header's credentials, whatever their scheme.
    (re.compile(r"(?i)\b(authorization\s*[:=]\s*\w+)\s+\S+"), r"\1 [redacted]"),
    (re.compile(r"(?i)\b(bearer|basic)\s+[\w.~+/=-]+"), r"\1 [redacted]"),
    # A secret given by name, outside a URL: api_key=..., token: ..., "password": "...".
    (
        re.compile(
            r"(?i)\b((?:api[_-]?key|access[_-]?token|token|secret|password)[\"']?\s*[:=]\s*[\"']?)"
            r"[^\s\"',}]+"
        ),
        r"\1[redacted]",
    ),
    # Tokens in the shapes their issuers give them: provider keys, GitHub's, and JWTs.
    (re.compile(r"\b(?:sk|pk|rk|key)-[\w-]{8,}"), "[redacted]"),
    (re.compile(r"\b(?:gh[pousr]_\w{20,}|github_pat_\w{20,})"), "[redacted]"),
    (re.compile(r"\beyJ[\w-]+\.eyJ[\w-]+\.[\w-]+"), "[redacted]"),
)


def redacted(text: str) -> str:
    """Text with what looks like a secret taken out.

    A URL's credentials and query, an Authorization header's credentials, a secret given by
    name (``api_key=``, ``token:``), and tokens in their issuers' shapes (``sk-``, GitHub's,
    JWTs) go. What a run failed with, and a tool's errors and refusals, are recorded in the
    thread, which everyone who may read it reads.
    """
    for pattern, replacement in _SECRETS:
        text = pattern.sub(replacement, text)
    return text


def _reason(error: Exception) -> str | None:
    """Why a run failed, where it is known.

    A :class:`RunFailure` says why itself. ``tool_retries_exhausted`` is a model that kept
    calling a tool in ways it refused until no retries were left; ``unexpected_model_behavior``
    any other answer the run couldn't use, such as output no output type accepts.
    """
    if isinstance(error, RunFailure):
        return error.reason
    if not isinstance(error, UnexpectedModelBehavior):
        return None
    exhausted = error.message.startswith("Tool ") and "exceeded max retries" in error.message
    return "tool_retries_exhausted" if exhausted else "unexpected_model_behavior"


def _wrap(notes: list[Note]) -> str:
    return f"<workspace-changes>\n{render_notes(notes)}\n</workspace-changes>"


def _clip(text: str, limit: int) -> str:
    """Text cut to ``limit`` characters, its end marked; none at all for a limit of 0."""
    if limit <= 0:
        return ""
    return text if len(text) <= limit else text[: limit - 1] + "…"
