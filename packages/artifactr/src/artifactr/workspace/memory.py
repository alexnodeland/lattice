"""In-memory storage, for tests, examples and single-process prototypes.

It implements the full :class:`~artifactr.workspace.storage.Storage` protocol, including
transactions that roll back, a live log subscription and leases, but keeps nothing across
restarts and cannot be shared between processes.
"""

import asyncio
from collections.abc import AsyncGenerator, Callable, Collection, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from artifactr.core import (
    Artifact,
    ArtifactId,
    CommitResult,
    Envelope,
    MessageId,
    Needs,
    Proposal,
    ProposalId,
    Revision,
    Run,
    RunId,
    RunStatus,
    State,
    Thread,
    ThreadId,
    Versioned,
    delivered_to,
)
from artifactr.core.actors import Actor
from artifactr.workspace.storage import HistoryChunk, Scope, seal

Clock = Callable[[], datetime]
"""Returns the current time; injectable so tests control expiry."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class _Data:
    artifacts: dict[ArtifactId, Versioned[Artifact]] = field(
        default_factory=dict[ArtifactId, Versioned[Artifact]]
    )
    revisions: dict[ArtifactId, list[Revision]] = field(
        default_factory=dict[ArtifactId, list[Revision]]
    )
    proposals: dict[ProposalId, Proposal] = field(default_factory=dict[ProposalId, Proposal])
    threads: dict[ThreadId, Thread] = field(default_factory=dict[ThreadId, Thread])
    runs: dict[RunId, Run] = field(default_factory=dict[RunId, Run])
    messages: set[MessageId] = field(default_factory=set[MessageId])
    log: list[Envelope] = field(default_factory=list[Envelope])
    history: dict[ThreadId, list[HistoryChunk]] = field(
        default_factory=dict[ThreadId, list[HistoryChunk]]
    )
    leases: dict[str, tuple[str, datetime]] = field(default_factory=dict[str, tuple[str, datetime]])
    cursors: dict[str, int] = field(default_factory=dict[str, int])
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    appended: asyncio.Condition = field(default_factory=asyncio.Condition)


class _Transaction:
    def __init__(self, data: _Data, scope: Scope, clock: Clock) -> None:
        self._data = data
        self._scope = scope
        self._clock = clock
        self._results: list[CommitResult] = []
        self._envelopes: list[Envelope] = []
        self._history: list[tuple[ThreadId, bytes]] = []

    async def load(self, needs: Needs) -> State:
        pending = _Data()
        for result in self._results:
            _apply(pending, result)
        # Earlier saves in this transaction are visible to later loads in it.
        return State(
            artifacts={
                i: _latest(pending.artifacts, self._data.artifacts, i) for i in needs.artifacts
            },
            proposals={
                i: _latest(pending.proposals, self._data.proposals, i) for i in needs.proposals
            },
            threads={i: _latest(pending.threads, self._data.threads, i) for i in needs.threads},
            runs={i: _latest(pending.runs, self._data.runs, i) for i in needs.runs},
            messages={i: i in pending.messages or i in self._data.messages for i in needs.messages},
        )

    async def save(
        self, result: CommitResult, *, actor: Actor, traceparent: str | None = None
    ) -> list[Envelope]:
        envelopes = seal(
            result.events,
            after_seq=len(self._data.log) + len(self._envelopes),
            scope=self._scope,
            actor=actor,
            ts=self._clock(),
            traceparent=traceparent,
        )
        self._results.append(result)
        self._envelopes.extend(envelopes)
        return envelopes

    async def append_history(self, thread_id: ThreadId, messages: bytes) -> None:
        self._history.append((thread_id, messages))

    def commit(self) -> None:
        for result in self._results:
            _apply(self._data, result)
        self._data.log.extend(self._envelopes)
        head = len(self._data.log)
        for thread_id, messages in self._history:
            chunk = HistoryChunk(seq=head, messages=messages)
            self._data.history.setdefault(thread_id, []).append(chunk)


def _latest[K, V](pending: dict[K, V], committed: dict[K, V], key: K) -> V | None:
    return pending[key] if key in pending else committed.get(key)


def _apply(data: _Data, result: CommitResult) -> None:
    for artifact in result.artifacts:
        data.artifacts[artifact.id] = artifact
    for revision in result.revisions:
        data.revisions.setdefault(revision.artifact_id, []).append(revision)
    for proposal in result.proposals:
        data.proposals[proposal.id] = proposal
    for thread in result.threads:
        data.threads[thread.id] = thread
    for run in result.runs:
        data.runs[run.id] = run
    data.messages.update(result.messages)


class InMemoryStorage:
    """Storage that keeps every workspace in process memory.

    Args:
        clock: Returns the current time. Defaults to the system clock in UTC.
    """

    def __init__(self, *, clock: Clock = _utc_now) -> None:
        self._workspaces: dict[Scope, _Data] = {}
        self._clock = clock

    def _data(self, scope: Scope) -> _Data:
        return self._workspaces.setdefault(scope, _Data())

    @asynccontextmanager
    async def transaction(self, scope: Scope) -> AsyncGenerator[_Transaction]:
        """Begin a transaction; it holds the workspace's lock until it ends."""
        data = self._data(scope)
        async with data.lock:
            transaction = _Transaction(data, scope, self._clock)
            yield transaction
            transaction.commit()
            async with data.appended:
                data.appended.notify_all()

    async def artifact(self, scope: Scope, artifact_id: ArtifactId) -> Versioned[Artifact] | None:
        """Return an artifact's current version, or None."""
        return self._data(scope).artifacts.get(artifact_id)

    async def artifacts(
        self, scope: Scope, *, kind: str | None = None, include_archived: bool = False
    ) -> list[Versioned[Artifact]]:
        """Return current artifacts, optionally of one kind, oldest first."""
        return [
            artifact
            for artifact in self._data(scope).artifacts.values()
            if (kind is None or artifact.kind == kind)
            and (include_archived or not artifact.archived)
        ]

    async def revisions(self, scope: Scope, artifact_id: ArtifactId) -> list[Revision]:
        """Return an artifact's revisions, oldest first."""
        return list(self._data(scope).revisions.get(artifact_id, []))

    async def thread(self, scope: Scope, thread_id: ThreadId) -> Thread | None:
        """Return a thread, or None."""
        return self._data(scope).threads.get(thread_id)

    async def threads(self, scope: Scope) -> list[Thread]:
        """Return every thread, oldest first."""
        return list(self._data(scope).threads.values())

    async def proposal(self, scope: Scope, proposal_id: ProposalId) -> Proposal | None:
        """Return a proposal, or None."""
        return self._data(scope).proposals.get(proposal_id)

    async def proposals(
        self,
        scope: Scope,
        *,
        status: Literal["pending", "accepted", "rejected"] | None = None,
    ) -> list[Proposal]:
        """Return proposals, optionally with one status, oldest first."""
        proposals = self._data(scope).proposals.values()
        return [p for p in proposals if status is None or p.status == status]

    async def run(self, scope: Scope, run_id: RunId) -> Run | None:
        """Return a run, or None."""
        return self._data(scope).runs.get(run_id)

    async def runs(
        self,
        scope: Scope,
        *,
        thread_id: ThreadId | None = None,
        status: RunStatus | None = None,
    ) -> list[Run]:
        """Return runs, optionally of one thread and with one status, oldest first."""
        return [
            run
            for run in self._data(scope).runs.values()
            if (thread_id is None or run.thread_id == thread_id)
            and (status is None or run.status == status)
        ]

    async def head_seq(self, scope: Scope) -> int:
        """Return the log's latest ``seq``, or 0 if it is empty."""
        return len(self._data(scope).log)

    async def read(
        self,
        scope: Scope,
        *,
        after_seq: int = 0,
        before_seq: int | None = None,
        threads: Collection[ThreadId] | None = None,
        limit: int | None = None,
        last: int | None = None,
    ) -> list[Envelope]:
        """Return logged envelopes in the window ``after_seq < seq < before_seq``, in order.

        Of those delivered to ``threads``, if given: the first ``limit`` or the last ``last``.
        """
        log = self._data(scope).log
        window = log[after_seq : len(log) if before_seq is None else max(before_seq - 1, 0)]
        found = [envelope for envelope in window if delivered_to(envelope, threads)]
        if last is not None:
            return found[max(len(found) - last, 0) :]
        return found if limit is None else found[:limit]

    async def subscribe(self, scope: Scope, *, after_seq: int = 0) -> AsyncGenerator[Envelope]:
        """Yield stored envelopes after ``after_seq``, then each new one as it commits."""
        data = self._data(scope)
        cursor = after_seq
        while True:
            batch = await self._next_batch(data, cursor)
            for envelope in batch:
                yield envelope
            cursor = batch[-1].seq

    @staticmethod
    async def _next_batch(data: _Data, cursor: int) -> list[Envelope]:
        async with data.appended:
            await data.appended.wait_for(lambda: len(data.log) > cursor)
            return data.log[cursor:]

    async def history(self, scope: Scope, thread_id: ThreadId) -> Sequence[HistoryChunk]:
        """Return a thread's history chunks, in the order they were appended."""
        return list(self._data(scope).history.get(thread_id, []))

    async def acquire_lease(self, scope: Scope, key: str, holder: str, ttl: timedelta) -> bool:
        """Take or renew an exclusive lease. Return False if another holder has it."""
        leases = self._data(scope).leases
        now = self._clock()
        current = leases.get(key)
        if current is not None and current[0] != holder and current[1] > now:
            return False
        leases[key] = (holder, now + ttl)
        return True

    async def release_lease(self, scope: Scope, key: str, holder: str) -> None:
        """Release a lease if ``holder`` has it."""
        leases = self._data(scope).leases
        if key in leases and leases[key][0] == holder:
            del leases[key]

    async def cursor(self, scope: Scope, name: str) -> int:
        """Return how far a named consumer of the log has got: the ``seq`` saved, or 0."""
        return self._data(scope).cursors.get(name, 0)

    async def save_cursor(self, scope: Scope, name: str, seq: int) -> None:
        """Save how far a named consumer of the log has got; a cursor only moves forward."""
        cursors = self._data(scope).cursors
        cursors[name] = max(cursors.get(name, 0), seq)
