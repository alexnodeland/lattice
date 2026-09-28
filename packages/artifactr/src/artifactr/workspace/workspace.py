"""Workspaces: tenant-scoped handles over artifacts, threads and the log (ADR-0011).

Every read and write goes through a :class:`Workspace`, and every write goes through
:meth:`Workspace.commit` or :meth:`Workspace.record`, which run core's rules inside one storage
transaction (ADR-0002, ADR-0018).
"""

import asyncio
import contextlib
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Collection, Iterable, Sequence
from datetime import timedelta
from typing import Literal, cast, overload

from artifactr.core import (
    Actor,
    Applied,
    ArchiveArtifact,
    Artifact,
    ArtifactId,
    Command,
    CommitResult,
    CreateArtifact,
    CreateThread,
    EditArtifact,
    Envelope,
    Fact,
    InvalidState,
    Note,
    NotFound,
    Outcome,
    PostMessage,
    Proposal,
    ProposalId,
    ProposeChange,
    Proposed,
    Recorded,
    Resolved,
    RespondToProposal,
    Revision,
    Run,
    RunId,
    State,
    TenantId,
    Thread,
    ThreadId,
    Versioned,
    WorkspaceId,
    change_notes,
    commit,
    create_artifact,
    delivered_to,
    needs,
    record,
)
from artifactr.core.commands import AnswerDeferred, SetFocus, SetThreadMode
from artifactr.workspace.storage import Scope, Storage


class ThreadBusy(InvalidState):
    """Another run holds the thread."""


class Workspaces:
    """Opens scoped :class:`Workspace` handles over one storage.

    Args:
        storage: Where workspaces are kept.
        types: The artifact types this application accepts. Others are rejected even if they
            are registered, so clients cannot create arbitrary types. ``None`` accepts every
            registered type.
    """

    def __init__(self, storage: Storage, *, types: Iterable[type[Artifact]] | None = None) -> None:
        self._storage = storage
        self._kinds = None if types is None else frozenset(t.kind for t in types)

    async def open(
        self, tenant_id: TenantId, workspace_id: WorkspaceId, *, actor: Actor
    ) -> "Workspace":
        """Return a handle on a tenant's workspace, acting as ``actor``.

        This is the only place a tenant id enters; nothing on the handle can reach another
        tenant.
        """
        return Workspace(self._storage, Scope(tenant_id, workspace_id), actor, self._kinds)


class Workspace:
    """A handle on one tenant's workspace, bound to the actor it acts as.

    Create handles with :meth:`Workspaces.open`, and derive handles for other actors (such as
    the agent) with :meth:`as_actor`.
    """

    def __init__(
        self, storage: Storage, scope: Scope, actor: Actor, kinds: frozenset[str] | None
    ) -> None:
        self._storage = storage
        self._scope = scope
        self._actor = actor
        self._kinds = kinds

    @property
    def workspace_id(self) -> WorkspaceId:
        """The workspace's id."""
        return self._scope.workspace_id

    @property
    def actor(self) -> Actor:
        """Who this handle acts as."""
        return self._actor

    def as_actor(self, actor: Actor) -> "Workspace":
        """Return a handle on the same workspace that acts as ``actor``."""
        return Workspace(self._storage, self._scope, actor, self._kinds)

    # ─── writes ───────────────────────────────────────────────────────────────

    @overload
    async def commit(
        self, command: CreateArtifact | EditArtifact | ArchiveArtifact
    ) -> Applied | Proposed: ...

    @overload
    async def commit(self, command: ProposeChange) -> Proposed: ...

    @overload
    async def commit(self, command: RespondToProposal) -> Resolved: ...

    @overload
    async def commit(
        self, command: CreateThread | PostMessage | SetFocus | SetThreadMode | AnswerDeferred
    ) -> Recorded: ...

    async def commit(self, command: Command) -> Outcome:
        """Submit a command.

        Returns:
            What the command did, with the ``seq`` of the last event it appended.

        Raises:
            Rejection: If the command cannot be applied.
        """
        self._check_kind(command)
        return await self._execute(command, lambda state: commit(command, state, actor=self._actor))

    async def record(self, fact: Fact, *, history: bytes | None = None) -> Recorded:
        """Record a fact about an agent run, or an application event.

        Args:
            fact: The fact to record.
            history: Serialized model messages to append to the fact's thread history in the
                same transaction, typically with ``RunPaused`` or ``RunEnded``.
        """
        outcome = await self._execute(
            fact,
            lambda state: record(fact, state, actor=self._actor),
            history=(fact.thread_id, history) if history is not None and fact.thread_id else None,
        )
        return cast("Recorded", outcome)

    async def create(
        self,
        artifact: Artifact,
        *,
        artifact_id: ArtifactId | None = None,
        thread_id: ThreadId | None = None,
    ) -> Applied | Proposed:
        """Create an artifact from an instance of its type."""
        return await self.commit(
            create_artifact(artifact, artifact_id=artifact_id, thread_id=thread_id)
        )

    async def create_thread(self, title: str = "") -> Thread:
        """Create a thread and return it."""
        command = CreateThread(title=title)
        await self.commit(command)
        return await self.thread(command.thread_id)

    async def post_message(self, thread_id: ThreadId, content: str) -> Recorded:
        """Post a message in a thread as this handle's actor."""
        return await self.commit(PostMessage(thread_id=thread_id, content=content))

    async def _execute(
        self,
        item: Command | Fact,
        decide: Callable[[State], CommitResult],
        *,
        history: tuple[ThreadId, bytes] | None = None,
    ) -> Outcome:
        async with self._storage.transaction(self._scope) as transaction:
            state = State()
            while missing := needs(item, actor=self._actor, state=state):
                state = _merge(state, await transaction.load(missing))
            result = decide(state)
            envelopes = await transaction.save(result, actor=self._actor)
            if history is not None:
                await transaction.append_history(*history)
        if not envelopes:
            return result.outcome
        return result.outcome.model_copy(update={"seq": envelopes[-1].seq})

    def _check_kind(self, command: Command) -> None:
        if self._kinds is None:
            return
        created = command.change if isinstance(command, ProposeChange) else command
        if isinstance(created, CreateArtifact) and created.kind not in self._kinds:
            raise NotFound("artifact type", created.kind)

    # ─── reads ────────────────────────────────────────────────────────────────

    async def get[A: Artifact](
        self, artifact_type: type[A], artifact_id: ArtifactId
    ) -> Versioned[A]:
        """Return an artifact's current version, checked to be of ``artifact_type``.

        Raises:
            NotFound: If there is no such artifact of that type.
        """
        artifact = await self._storage.artifact(self._scope, artifact_id)
        if artifact is None or not isinstance(artifact.data, artifact_type):
            raise NotFound(getattr(artifact_type, "kind", "artifact"), artifact_id)
        return cast("Versioned[A]", artifact)

    async def artifact(self, artifact_id: ArtifactId) -> Versioned[Artifact]:
        """Return an artifact's current version, whatever its type.

        Raises:
            NotFound: If there is no such artifact.
        """
        return await self.get(Artifact, artifact_id)

    async def artifacts[A: Artifact](
        self, artifact_type: type[A] = Artifact, *, include_archived: bool = False
    ) -> list[Versioned[A]]:
        """Return current artifacts that are instances of ``artifact_type``, oldest first."""
        artifacts = await self._storage.artifacts(self._scope, include_archived=include_archived)
        return [
            cast("Versioned[A]", artifact)
            for artifact in artifacts
            if isinstance(artifact.data, artifact_type)
        ]

    async def revisions(self, artifact_id: ArtifactId) -> list[Revision]:
        """Return an artifact's revisions, oldest first."""
        return await self._storage.revisions(self._scope, artifact_id)

    async def thread(self, thread_id: ThreadId) -> Thread:
        """Return a thread.

        Raises:
            NotFound: If there is no such thread.
        """
        thread = await self._storage.thread(self._scope, thread_id)
        if thread is None:
            raise NotFound("thread", thread_id)
        return thread

    async def threads(self) -> list[Thread]:
        """Return every thread, oldest first."""
        return await self._storage.threads(self._scope)

    async def proposal(self, proposal_id: ProposalId) -> Proposal:
        """Return a proposal.

        Raises:
            NotFound: If there is no such proposal.
        """
        proposal = await self._storage.proposal(self._scope, proposal_id)
        if proposal is None:
            raise NotFound("proposal", proposal_id)
        return proposal

    async def proposals(
        self, *, status: Literal["pending", "accepted", "rejected"] | None = "pending"
    ) -> list[Proposal]:
        """Return proposals with a status (pending by default; None for all), oldest first."""
        return await self._storage.proposals(self._scope, status=status)

    async def run(self, run_id: RunId) -> Run:
        """Return a run.

        Raises:
            NotFound: If there is no such run.
        """
        run = await self._storage.run(self._scope, run_id)
        if run is None:
            raise NotFound("run", run_id)
        return run

    async def history(self, thread_id: ThreadId) -> Sequence[bytes]:
        """Return a thread's serialized model messages, one chunk per recorded run segment."""
        return await self._storage.history(self._scope, thread_id)

    # ─── the log ──────────────────────────────────────────────────────────────

    async def head_seq(self) -> int:
        """Return the log's latest ``seq``, or 0 if it is empty."""
        return await self._storage.head_seq(self._scope)

    async def read(
        self,
        *,
        after_seq: int = 0,
        threads: Collection[ThreadId] | None = None,
        limit: int | None = None,
    ) -> list[Envelope]:
        """Return logged envelopes after ``after_seq``, in order.

        Args:
            after_seq: Return envelopes with a greater ``seq``.
            threads: Only thread-scoped events from these threads; workspace-scoped events
                (artifacts, proposals) are always included. ``None`` includes every thread.
            limit: The most envelopes to return.
        """
        envelopes = await self._storage.read(self._scope, after_seq=after_seq)
        matching = [envelope for envelope in envelopes if delivered_to(envelope, threads)]
        return matching if limit is None else matching[:limit]

    async def subscribe(
        self, *, after_seq: int = 0, threads: Collection[ThreadId] | None = None
    ) -> AsyncIterator[Envelope]:
        """Yield envelopes after ``after_seq``: the stored ones, then new ones as they commit.

        Replay and live delivery are the same stream, so nothing falls between them.
        """
        async for envelope in self._storage.subscribe(self._scope, after_seq=after_seq):
            if delivered_to(envelope, threads):
                yield envelope

    async def change_notes(
        self,
        *,
        after_seq: int,
        focus: Collection[ArtifactId] | None = None,
        viewer: Actor | None = None,
    ) -> list[Note]:
        """Return notes about what others did since ``after_seq``.

        Args:
            after_seq: Only consider envelopes with a greater ``seq``.
            focus: The artifacts the viewer follows; ``None`` means all.
            viewer: Who the notes are for; defaults to this handle's actor.
        """
        envelopes = await self._storage.read(self._scope, after_seq=after_seq)
        return change_notes(envelopes, viewer=viewer or self._actor, focus=focus)

    # ─── runs ─────────────────────────────────────────────────────────────────

    @contextlib.asynccontextmanager
    async def claim_thread(
        self, thread_id: ThreadId, *, holder: str, ttl: timedelta = timedelta(seconds=30)
    ) -> AsyncGenerator[None]:
        """Hold a thread exclusively, renewing the claim until the block exits.

        One run is active per thread. The claim is a lease in storage, so it holds across
        processes and lapses by itself if the holder dies.

        Raises:
            ThreadBusy: If another holder has the thread.
        """
        key = f"thread:{thread_id}"
        if not await self._storage.acquire_lease(self._scope, key, holder, ttl):
            raise ThreadBusy(f"thread {thread_id} is busy with another run")
        renewal = asyncio.create_task(self._renew(key, holder, ttl))
        try:
            yield
        finally:
            renewal.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await renewal
            await self._storage.release_lease(self._scope, key, holder)

    async def _renew(self, key: str, holder: str, ttl: timedelta) -> None:
        while True:
            await asyncio.sleep(ttl.total_seconds() / 3)
            await self._storage.acquire_lease(self._scope, key, holder, ttl)


def _merge(state: State, loaded: State) -> State:
    return State(
        artifacts={**state.artifacts, **loaded.artifacts},
        proposals={**state.proposals, **loaded.proposals},
        threads={**state.threads, **loaded.threads},
        runs={**state.runs, **loaded.runs},
    )
