"""The storage protocol: where a workspace's state and log live.

artifactr ships two implementations: :class:`~artifactr.workspace.InMemoryStorage` for tests
and examples, and ``artifactr.sql.SqlStorage`` for production. Applications with other needs
implement :class:`Storage` themselves; the workspace behaviour suite in the test tree shows
what an implementation must do.
"""

from collections.abc import AsyncIterator, Sequence
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
        """Load the requested entities. Ids that do not exist map to ``None``."""
        ...

    async def save(self, result: CommitResult, *, actor: Actor) -> list[Envelope]:
        """Persist a result's entities and revisions, and append its events to the log.

        Returns:
            The appended envelopes, with their ``seq`` numbers assigned.
        """
        ...

    async def append_history(self, thread_id: ThreadId, messages: bytes) -> None:
        """Append serialized model messages to a thread's history."""
        ...


class Storage(Protocol):
    """Persistence for workspaces. Every method is scoped to one tenant's workspace."""

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
        self, scope: Scope, *, after_seq: int = 0, limit: int | None = None
    ) -> list[Envelope]:
        """Return logged envelopes with ``seq`` greater than ``after_seq``, in order."""
        ...

    def subscribe(self, scope: Scope, *, after_seq: int = 0) -> AsyncIterator[Envelope]:
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
