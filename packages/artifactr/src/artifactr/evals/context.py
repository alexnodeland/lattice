"""What feedback, or an evaluation, is about: a target's context, read from the log.

A context is read as of the end of its target, so an evaluator's input is the same whether it is
built for a dataset, long after, or online, as the turn ends (ADR-0044):

- a turn: up to the run's last event
- a message: up to the message
- an artifact version: up to the change that made it
- a thread: up to the feedback, or up to now
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import assert_never

from artifactr.core import (
    Artifact,
    ArtifactArchived,
    ArtifactChanged,
    ArtifactCreated,
    ArtifactId,
    ArtifactTarget,
    Envelope,
    FeedbackGiven,
    FeedbackTarget,
    FocusChanged,
    MessagePosted,
    MessageTarget,
    Revision,
    RunId,
    RunStarted,
    Thread,
    ThreadId,
    ThreadTarget,
    TraceId,
    TurnTarget,
    Versioned,
    load_versioned,
)
from artifactr.workspace import Workspace

type BuildTurnInput[InputT] = Callable[["TargetContext"], InputT | Awaitable[InputT]]
"""Turns a target's context into an evaluator's input; sync or async."""

_CHANGES = (ArtifactCreated, ArtifactChanged, ArtifactArchived)


@dataclass(frozen=True, kw_only=True)
class TargetContext:
    """What a piece of feedback, or an evaluation, is about, as the log recorded it.

    Attributes:
        workspace: The workspace, for builders that read more of it.
        target: What the feedback or the evaluation is about.
        seq: The log position the context is read at: the end of the target.
        thread: The thread the target belongs to, as it is now; ``None`` for an artifact
            version written outside any thread.
        transcript: The thread's ``message_posted`` envelopes up to ``seq``, oldest first.
        events: The run's envelopes up to ``seq``, for a turn, a message the agent posted, or an
            artifact version the agent wrote: its tool calls, messages, changes and proposals.
        artifacts: The artifacts the thread followed at ``seq``, each at its version then.
        revision: The version, for an artifact target.
        artifact: The version as its artifact type, for an artifact target.
        trace_id: The trace the target was produced in, when it was traced: the turn's latest
            attempt, or the commit of the artifact version.
    """

    workspace: Workspace
    target: FeedbackTarget
    seq: int
    thread: Thread | None = None
    transcript: tuple[Envelope, ...] = ()
    events: tuple[Envelope, ...] = ()
    artifacts: tuple[Versioned[Artifact], ...] = ()
    revision: Revision | None = None
    artifact: Versioned[Artifact] | None = None
    trace_id: TraceId | None = None


async def target_context(workspace: Workspace, target: FeedbackTarget) -> TargetContext:
    """Read what a target is about from the workspace's log, as of the target's end.

    Raises:
        NotFound: If the target's run, thread or artifact does not exist.
    """
    log = await workspace.read()
    return await read_context(workspace, target, log, limit=log[-1].seq if log else 0)


async def read_context(
    workspace: Workspace, target: FeedbackTarget, log: Sequence[Envelope], *, limit: int
) -> TargetContext:
    """Build a target's context from a snapshot of the log, ignoring envelopes after ``limit``."""
    seen = [envelope for envelope in log if envelope.seq <= limit]
    revision: Revision | None = None
    match target:
        case ThreadTarget():
            thread_id, run_id, seq = target.thread_id, None, limit
        case TurnTarget():
            run = await workspace.run(target.run_id)
            turn = _run_events(seen, run.id)
            thread_id, run_id, seq = run.thread_id, run.id, turn[-1].seq if turn else limit
        case MessageTarget():
            posted = [
                envelope.seq
                for envelope in seen
                if isinstance(envelope.event, MessagePosted)
                and envelope.event.message_id == target.message_id
            ]
            thread_id, run_id, seq = target.thread_id, target.run_id, min(posted, default=limit)
        case ArtifactTarget():
            made = next(
                envelope
                for envelope in seen
                if isinstance(envelope.event, _CHANGES)
                and envelope.event.artifact_id == target.artifact_id
                and envelope.event.version == target.version
            )
            thread_id, run_id, seq = made.thread_id, made.run_id, made.seq
            revision = await _revision(workspace, target.artifact_id, target.version)
        case _:
            assert_never(target)
    upto = [envelope for envelope in seen if envelope.seq <= seq]
    events = _run_events(upto, run_id) if run_id else ()
    traces = [
        e.event.trace_id for e in events if isinstance(e.event, RunStarted) and e.event.trace_id
    ]
    return TargetContext(
        workspace=workspace,
        target=target,
        seq=seq,
        thread=await workspace.thread(thread_id) if thread_id else None,
        transcript=tuple(
            envelope
            for envelope in upto
            if isinstance(envelope.event, MessagePosted) and envelope.event.thread_id == thread_id
        ),
        events=events,
        artifacts=await _followed(workspace, upto, thread_id),
        revision=revision,
        artifact=_versioned(revision) if revision else None,
        trace_id=revision.trace_id if revision else (traces[-1] if traces else None),
    )


def _run_events(log: Sequence[Envelope], run_id: RunId) -> tuple[Envelope, ...]:
    """A run's envelopes, without the feedback given on it afterwards."""
    return tuple(
        envelope
        for envelope in log
        if envelope.run_id == run_id and not isinstance(envelope.event, FeedbackGiven)
    )


async def _followed(
    workspace: Workspace, log: Sequence[Envelope], thread_id: ThreadId | None
) -> tuple[Versioned[Artifact], ...]:
    """The artifacts a thread followed at the end of ``log``, each at its version then."""
    focus: tuple[ArtifactId, ...] = ()
    versions: dict[ArtifactId, int] = {}
    for envelope in log:
        event = envelope.event
        if isinstance(event, FocusChanged) and event.thread_id == thread_id:
            focus = event.artifact_ids
        elif isinstance(event, _CHANGES):
            versions[event.artifact_id] = event.version
    return tuple(
        [
            _versioned(await _revision(workspace, artifact_id, versions[artifact_id]))
            for artifact_id in focus
        ]
    )


async def _revision(workspace: Workspace, artifact_id: ArtifactId, version: int) -> Revision:
    revisions = await workspace.revisions(artifact_id)
    return next(revision for revision in revisions if revision.version == version)


def _versioned(revision: Revision) -> Versioned[Artifact]:
    """A revision as its artifact type, at its version."""
    return load_versioned(
        id=revision.artifact_id,
        kind=revision.kind,
        version=revision.version,
        data=revision.data,
        updated_by=revision.actor,
        archived=revision.archived,
    )
