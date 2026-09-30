"""The storage protocol: where a workspace's state and log live.

artifactr ships two implementations: :class:`~artifactr.workspace.InMemoryStorage` for tests
and examples, and ``artifactr.sql.SqlStorage`` for production. Applications with other needs
implement :class:`Storage` themselves; the workspace behaviour suite in the test tree shows
what an implementation must do.
"""

from collections.abc import AsyncGenerator, Collection, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal, Protocol

from artifactr.core import (
    Artifact,
    ArtifactId,
    CommitResult,
    Envelope,
    Needs,
    Proposal,
    ProposalId,
    Revision,
    Run,
    RunId,
    RunStatus,
    State,
    TenantId,
    Thread,
    ThreadId,
    Versioned,
    WorkspaceId,
)
from artifactr.core.actors import Actor


@dataclass(frozen=True)
class HistoryChunk:
    """Serialized model messages from one run segment, and the ``seq`` they were saved at."""

    seq: int
    """The log's head when the chunk was saved: everything up to it happened before."""

    messages: bytes


@dataclass(frozen=True)
class Scope:
    """A tenant's workspace: the unit of isolation, ordering and locking."""

    tenant_id: TenantId
    workspace_id: WorkspaceId


class Transaction(Protocol):
    """One atomic unit of work on a workspace.

    A transaction must be serialized with respect to every other transaction on the same
    scope from the moment it begins, so what it loads cannot change before it saves. The
    in-memory storage holds a per-workspace lock; SQL storage locks the workspace row.
    """

    async def load(self, needs: Needs) -> State:
        """Load the requested entities, and whether the requested message ids are used.

        Entity ids that do not exist map to ``None``.
        """
        ...

    async def save(
        self, result: CommitResult, *, actor: Actor, traceparent: str | None = None
    ) -> list[Envelope]:
        """Persist a result's entities, revisions and used message ids, and log its events.

        Args:
            result: What core decided.
            actor: Who the envelopes are attributed to.
            traceparent: The W3C trace context the envelopes record.

        Returns:
            The appended envelopes, with their ``seq`` numbers assigned.
        """
        ...

    async def append_history(self, thread_id: ThreadId, messages: bytes) -> None:
        """Append serialized model messages to a thread's history."""
        ...


class Storage(Protocol):
    """Persistence for workspaces. Every method is scoped to one tenant's workspace.

    A caller can be cancelled at any await, by a stopped run, a timeout or a closed connection,
    so every method is cancel-safe: a cancelled caller leaves no lock or connection behind;
    cancellation may be deferred until the current statement ends. So a cancelled call may still
    have taken effect: a transaction may have committed, or ``acquire_lease`` taken the lease. A
    wait for a pooled connection cannot be interrupted either, so a task that holds a
    transaction must not await a task it cancelled. The event loop's shutdown is not covered: it
    cancels the storage's own tasks too, so stop runs with ``Runner.aclose`` first.
    """

    def transaction(self, scope: Scope) -> AbstractAsyncContextManager[Transaction]:
        """Begin a transaction that commits when the block exits normally."""
        ...

    async def artifact(self, scope: Scope, artifact_id: ArtifactId) -> Versioned[Artifact] | None:
        """Return an artifact's current version, or None."""
        ...

    async def artifacts(
        self, scope: Scope, *, kind: str | None = None, include_archived: bool = False
    ) -> list[Versioned[Artifact]]:
        """Return current artifacts, optionally of one kind, oldest first."""
        ...

    async def revisions(self, scope: Scope, artifact_id: ArtifactId) -> list[Revision]:
        """Return an artifact's revisions, oldest first."""
        ...

    async def thread(self, scope: Scope, thread_id: ThreadId) -> Thread | None:
        """Return a thread, or None."""
        ...

    async def threads(self, scope: Scope) -> list[Thread]:
        """Return every thread, oldest first."""
        ...

    async def proposal(self, scope: Scope, proposal_id: ProposalId) -> Proposal | None:
        """Return a proposal, or None."""
        ...

    async def proposals(
        self,
        scope: Scope,
        *,
        status: Literal["pending", "accepted", "rejected"] | None = None,
    ) -> list[Proposal]:
        """Return proposals, optionally with one status, oldest first."""
        ...

    async def run(self, scope: Scope, run_id: RunId) -> Run | None:
        """Return a run, or None."""
        ...

    async def runs(
        self,
        scope: Scope,
        *,
        thread_id: ThreadId | None = None,
        status: RunStatus | None = None,
    ) -> list[Run]:
        """Return runs, optionally of one thread and with one status, oldest first."""
        ...

    async def head_seq(self, scope: Scope) -> int:
        """Return the log's latest ``seq``, or 0 if it is empty."""
        ...

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

        Args:
            scope: The workspace whose log to read.
            after_seq: Only envelopes after this ``seq``.
            before_seq: Only envelopes before this ``seq``; ``None`` reads to the head.
            threads: Only the envelopes a subscriber following these threads receives, by
                :func:`~artifactr.core.delivered_to`'s rule; ``None`` reads every thread.
            limit: At most this many: the first ones in the window that match.
            last: At most this many: the last ones in the window that match, still returned
                in order. This is the tail of the log.

        Callers give at most one of ``limit`` and ``last``, and no negative numbers;
        :meth:`~artifactr.workspace.Workspace.read` checks.
        """
        ...

    def subscribe(self, scope: Scope, *, after_seq: int = 0) -> AsyncGenerator[Envelope]:
        """Yield envelopes with ``seq`` greater than ``after_seq``.

        First the stored ones, then each new one as it is committed. The iterator runs until
        it is closed.
        """
        ...

    async def history(self, scope: Scope, thread_id: ThreadId) -> Sequence[HistoryChunk]:
        """Return a thread's history chunks, in the order they were appended."""
        ...

    async def acquire_lease(self, scope: Scope, key: str, holder: str, ttl: timedelta) -> bool:
        """Take or renew an exclusive lease. Return False if another holder has it."""
        ...

    async def release_lease(self, scope: Scope, key: str, holder: str) -> None:
        """Release a lease if ``holder`` has it."""
        ...

    async def cursor(self, scope: Scope, name: str) -> int:
        """Return how far a named consumer of the log has got: the ``seq`` saved, or 0."""
        ...

    async def save_cursor(self, scope: Scope, name: str, seq: int) -> None:
        """Save how far a named consumer of the log has got, such as a feedback mirror.

        A cursor only moves forward: saving a ``seq`` below the saved one leaves it, so a
        consumer running in several processes cannot move it back.
        """
        ...
