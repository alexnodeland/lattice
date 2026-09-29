"""The feedback mirror: a subscriber on a workspace's log that sends feedback to a score sink.

Each ``feedback_given`` becomes one score per scored field, attached to the trace it is about:

- a turn: the trace of the run's latest attempt, the one that ended or paused it
- a message: the trace of the run that posted it, when the target names the run
- an artifact version: the trace it was committed in (ADR-0033)
- a thread, or anything without a trace: the session, which is the thread

Score ids are derived from the envelope's id and the field, so mirroring the same log again
replaces scores instead of duplicating them: the mirror can always start over from the
beginning.
"""

import uuid
from typing import assert_never

from artifactr.core import (
    AgentActor,
    ArtifactTarget,
    Envelope,
    Feedback,
    FeedbackGiven,
    MessageTarget,
    RunId,
    ThreadTarget,
    TraceId,
    TurnTarget,
    feedback_types,
)
from artifactr.scores.mapping import score_configs, score_values
from artifactr.scores.ports import Score, ScoreConfigStore, ScoreSink
from artifactr.workspace import Workspace

_SCORE_IDS = uuid.UUID("8d0e3b5c-3f7a-4a51-9c1e-6f2b7d4a9e10")
"""The namespace of score ids."""


class FeedbackMirror:
    """Sends a workspace's feedback to a score sink.

    Args:
        workspace: The workspace to follow; any actor's handle will do, since it only reads.
        sink: Where scores go.
    """

    def __init__(self, workspace: Workspace, sink: ScoreSink) -> None:
        self._workspace = workspace
        self._sink = sink

    async def follow(self, *, after_seq: int = 0) -> None:
        """Mirror feedback after ``after_seq``, then each new piece as it is given, until cancelled.

        Run it as a task for as long as the workspace should be mirrored.
        """
        async for envelope in self._workspace.subscribe(after_seq=after_seq):
            await self.mirror(envelope)

    async def mirror(self, envelope: Envelope) -> list[Score]:
        """Send the scores of one envelope, and return them; other events send nothing."""
        scores = await self.scores(envelope)
        for score in scores:
            await self._sink.send(score)
        return scores

    async def scores(self, envelope: Envelope) -> list[Score]:
        """Return the scores of a ``feedback_given`` envelope.

        There are none for other events, for a feedback type this process does not register,
        or for feedback with neither a trace nor a session to attach to.
        """
        event = envelope.event
        if not isinstance(event, FeedbackGiven):
            return []
        feedback_type = feedback_types().get(event.feedback_type)
        if feedback_type is None:
            return []
        trace_id, session_id = await self._attachment(event)
        if trace_id is None and session_id is None:
            return []
        metadata = {
            "tenant_id": self._workspace.tenant_id,
            "workspace_id": self._workspace.workspace_id,
            "feedback_type": event.feedback_type,
            "target": event.target.kind,
            "actor": envelope.actor.participant,
            "actor_kind": envelope.actor.kind,
            "seq": str(envelope.seq),
        }
        return [
            Score(
                id=str(uuid.uuid5(_SCORE_IDS, f"{envelope.id}/{config.name}")),
                name=config.name,
                value=value,
                data_type=config.data_type,
                trace_id=trace_id,
                session_id=None if trace_id else session_id,
                timestamp=envelope.ts,
                metadata=metadata,
            )
            for config, value in score_values(feedback_type, event.value)
        ]

    async def _attachment(self, event: FeedbackGiven) -> tuple[TraceId | None, str | None]:
        """The trace and the session a piece of feedback is about."""
        target = event.target
        match target:
            case ThreadTarget():
                return None, target.thread_id
            case TurnTarget():
                return await self._run_trace(target.run_id), event.thread_id
            case MessageTarget():
                trace = await self._run_trace(target.run_id) if target.run_id else None
                return trace, target.thread_id
            case ArtifactTarget():
                revisions = await self._workspace.revisions(target.artifact_id)
                revision = next(r for r in revisions if r.version == target.version)
                author = revision.actor
                session = author.thread_id if isinstance(author, AgentActor) else None
                return revision.trace_id, session
            case _:
                assert_never(target)

    async def _run_trace(self, run_id: RunId) -> TraceId | None:
        # The run exists: core checked it when the feedback was given, and runs are kept.
        run = await self._workspace.run(run_id)
        return run.trace_ids[-1] if run.trace_ids else None


async def sync_score_configs(
    store: ScoreConfigStore, types: list[type[Feedback]] | None = None
) -> list[str]:
    """Create the score configs of feedback types that a store does not have yet.

    Args:
        store: Where the configs live.
        types: The feedback types; every registered type by default.

    Returns:
        The names of the configs created.
    """
    existing = set(await store.names())
    created: list[str] = []
    for feedback_type in types if types is not None else list(feedback_types().values()):
        for config in score_configs(feedback_type):
            if config.name not in existing:
                await store.create(config)
                existing.add(config.name)
                created.append(config.name)
    return created
