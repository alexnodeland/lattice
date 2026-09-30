"""Workspaces: tenant-scoped handles over artifacts, threads and the log (ADR-0011).

Every read and write goes through a :class:`Workspace`, and every write goes through
:meth:`Workspace.commit` or :meth:`Workspace.record`, which run core's rules inside one storage
transaction (ADR-0002, ADR-0018). Each commit is traced as an ``artifactr.commit {type}``
span, and what commits and facts do is counted in artifactr's metrics. Every envelope records
the W3C trace context of the span it was committed in, and every revision that span's trace
(ADR-0033).
"""

import asyncio
import contextlib
import dataclasses
import logging
import time
from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Awaitable,
    Callable,
    Collection,
    Iterable,
    Sequence,
)
from datetime import timedelta
from typing import Literal, cast, overload

from opentelemetry.metrics import MeterProvider
from opentelemetry.trace import StatusCode, TracerProvider

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
    Forbidden,
    GiveFeedback,
    InvalidState,
    MessageId,
    Note,
    NotFound,
    Outcome,
    PostMessage,
    Proposal,
    ProposalId,
    ProposeChange,
    Proposed,
    Recorded,
    Rejection,
    Resolved,
    RespondToProposal,
    Revision,
    Run,
    RunId,
    RunStatus,
    State,
    TenantId,
    Thread,
    ThreadId,
    ValidationFailed,
    Versioned,
    WorkspaceId,
    change_notes,
    commit,
    create_artifact,
    delivered_to,
    needs,
    new_message_id,
    record,
)
from artifactr.core.commands import AnswerDeferred, SetFocus, SetThreadMode
from artifactr.telemetry import (
    Telemetry,
    command_attributes,
    current_trace_id,
    current_traceparent,
    outcome_attributes,
    record_events,
)
from artifactr.telemetry.attributes import (
    ACTOR_KIND,
    COMMAND_TYPE,
    ERROR_TYPE,
    OUTCOME,
    REJECTION,
    TENANT_ID,
    WORKSPACE_ID,
)
from artifactr.telemetry.metrics import COMMANDS, COMMIT_DURATION
from artifactr.telemetry.traces import untraced
from artifactr.workspace.storage import HistoryChunk, Scope, Storage

logger = logging.getLogger("artifactr.workspace")

Authorize = Callable[[TenantId, WorkspaceId, Actor], Awaitable[bool]]
"""Decides whether an actor may use a workspace of its tenant.

The surfaces that serve workspaces, the FastAPI router and the MCP server, take one as their
``authorize`` hook, and pass it to :meth:`Workspaces.open` for every request that names a
workspace.
"""


class ThreadBusy(InvalidState):
    """Another run holds the thread."""


class Workspaces:
    """Opens scoped :class:`Workspace` handles over one storage.

    Args:
        storage: Where workspaces are kept.
        types: The artifact types this application accepts. Others are rejected even if they
            are registered, so clients cannot create arbitrary types. ``None`` accepts every
            registered type.
        tracer_provider: Where commit spans go. Defaults to the global tracer provider.
        meter_provider: Where artifactr's metrics go. Defaults to the global meter provider.
    """

    def __init__(
        self,
        storage: Storage,
        *,
        types: Iterable[type[Artifact]] | None = None,
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None = None,
    ) -> None:
        self._storage = storage
        self._kinds = None if types is None else frozenset(t.kind for t in types)
        self._telemetry = Telemetry(tracer_provider=tracer_provider, meter_provider=meter_provider)

    async def open(
        self,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        *,
        actor: Actor,
        authorize: Authorize | None = None,
    ) -> "Workspace":
        """Return a handle on a tenant's workspace, acting as ``actor``.

        This is the only place a tenant id enters; nothing on the handle can reach another
        tenant. The surfaces pass their ``authorize`` hook, so each refuses a workspace alike.

        Raises:
            Forbidden: If ``authorize`` is given and refuses the actor this workspace.
        """
        if authorize is not None and not await authorize(tenant_id, workspace_id, actor):
            raise Forbidden("this workspace is not yours to use")
        scope = Scope(tenant_id, workspace_id)
        return Workspace(self._storage, scope, actor, self._kinds, self._telemetry)


class Workspace:
    """A handle on one tenant's workspace, bound to the actor it acts as.

    Create handles with :meth:`Workspaces.open`, and derive handles for other actors (such as
    the agent) with :meth:`as_actor`.
    """

    def __init__(
        self,
        storage: Storage,
        scope: Scope,
        actor: Actor,
        kinds: frozenset[str] | None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._storage = storage
        self._scope = scope
        self._actor = actor
        self._kinds = kinds
        self._telemetry = telemetry or Telemetry()
        self._tenancy = {TENANT_ID: scope.tenant_id, WORKSPACE_ID: scope.workspace_id}

    @property
    def tenant_id(self) -> TenantId:
        """The id of the tenant the workspace belongs to."""
        return self._scope.tenant_id

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
        return Workspace(self._storage, self._scope, actor, self._kinds, self._telemetry)

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
        self,
        command: CreateThread
        | PostMessage
        | SetFocus
        | SetThreadMode
        | AnswerDeferred
        | GiveFeedback,
    ) -> Recorded: ...

    async def commit(self, command: Command) -> Outcome:
        """Submit a command.

        Returns:
            What the command did, with the ``seq`` of the last event it appended.

        Raises:
            Rejection: If the command cannot be applied.
        """
        attributes = command_attributes(
            command,
            tenant_id=self._scope.tenant_id,
            workspace_id=self._scope.workspace_id,
            actor=self._actor,
        )
        started = time.perf_counter()
        with self._telemetry.tracer.start_as_current_span(
            f"artifactr.commit {command.type}",
            attributes=attributes,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                self._check_kind(command)
                outcome = await self._transact(
                    command, lambda state: commit(command, state, actor=self._actor)
                )
            except Rejection as rejection:
                span.set_attributes({OUTCOME: "rejected", REJECTION: rejection.code})
                self._count(command, started, outcome="rejected", rejection=rejection.code)
                raise
            except Exception as error:
                span.record_exception(error)
                span.set_status(StatusCode.ERROR, str(error))
                span.set_attributes({OUTCOME: "error", ERROR_TYPE: type(error).__qualname__})
                self._count(command, started, outcome="error")
                raise
            span.set_attributes(outcome_attributes(outcome))
            self._count(command, started, outcome=outcome.type)
            return outcome

    def _count(
        self, command: Command, started: float, *, outcome: str, rejection: str | None = None
    ) -> None:
        attributes = {
            **self._tenancy,
            COMMAND_TYPE: command.type,
            OUTCOME: outcome,
            REJECTION: rejection,
            ACTOR_KIND: self._actor.kind,
        }
        self._telemetry.add(COMMANDS, 1, attributes)
        self._telemetry.record(COMMIT_DURATION, time.perf_counter() - started, attributes)

    async def record(self, fact: Fact, *, history: bytes | None = None) -> Recorded:
        """Record a fact about an agent run, or an application event.

        Args:
            fact: The fact to record.
            history: Serialized model messages to append to the fact's thread history in the
                same transaction, typically with ``RunPaused`` or ``RunEnded``.
        """
        outcome = await self._transact(
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

    async def post_message(
        self, thread_id: ThreadId, content: str, *, message_id: MessageId | None = None
    ) -> Recorded:
        """Post a message in a thread as this handle's actor.

        Args:
            thread_id: The thread to post in.
            content: What the message says.
            message_id: The message's id; a new one when omitted. An id already used in the
                workspace is refused with :class:`~artifactr.core.InvalidState`.
        """
        message = PostMessage(
            thread_id=thread_id, content=content, message_id=message_id or new_message_id()
        )
        return await self.commit(message)

    async def _transact(
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
            result = _traced(decide(state))
            envelopes = await transaction.save(
                result, actor=self._actor, traceparent=current_traceparent()
            )
            if history is not None:
                await transaction.append_history(*history)
        record_events(self._telemetry, result.events, actor=self._actor, scope=self._tenancy)
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
        self,
        artifact_type: type[A] = Artifact,
        *,
        kind: str | None = None,
        include_archived: bool = False,
    ) -> list[Versioned[A]]:
        """Return current artifacts that are instances of ``artifact_type``, oldest first.

        Args:
            artifact_type: Only artifacts of this type, or a subclass of it.
            kind: Only artifacts registered under this kind.
            include_archived: Archived artifacts too.
        """
        artifacts = await self._storage.artifacts(
            self._scope, kind=kind, include_archived=include_archived
        )
        return [
            cast("Versioned[A]", artifact)
            for artifact in artifacts
            if isinstance(artifact.data, artifact_type)
        ]

    async def revisions(self, artifact_id: ArtifactId) -> list[Revision]:
        """Return an artifact's revisions, oldest first.

        Raises:
            NotFound: If there is no such artifact: every artifact has a revision.
        """
        revisions = await self._storage.revisions(self._scope, artifact_id)
        if not revisions:
            raise NotFound("artifact", artifact_id)
        return revisions

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

    async def runs(
        self, *, thread_id: ThreadId | None = None, status: RunStatus | None = None
    ) -> list[Run]:
        """Return runs, optionally of one thread and with one status, oldest first."""
        return await self._storage.runs(self._scope, thread_id=thread_id, status=status)

    async def history(self, thread_id: ThreadId) -> Sequence[HistoryChunk]:
        """Return a thread's history: serialized model messages, one chunk per run segment."""
        return await self._storage.history(self._scope, thread_id)

    # ─── the log ──────────────────────────────────────────────────────────────

    async def head_seq(self) -> int:
        """Return the log's latest ``seq``, or 0 if it is empty."""
        return await self._storage.head_seq(self._scope)

    async def read(
        self,
        *,
        after_seq: int = 0,
        before_seq: int | None = None,
        threads: Collection[ThreadId] | None = None,
        limit: int | None = None,
        last: int | None = None,
    ) -> list[Envelope]:
        """Return logged envelopes in the window ``after_seq < seq < before_seq``, in order.

        Args:
            after_seq: Only envelopes after this ``seq``.
            before_seq: Only envelopes before this ``seq``; ``None`` reads to the head.
            threads: Only thread-scoped events from these threads; workspace-scoped events
                (artifacts, proposals) are always included. ``None`` includes every thread.
            limit: At most this many: the first ones in the window that match.
            last: At most this many: the last ones in the window that match, still in order.
                To page backwards, read ``last=n``, then ``last=n`` before the oldest ``seq``
                returned.

        Raises:
            ValidationFailed: If both ``limit`` and ``last`` are given, or a number is negative.
        """
        _check_page(after_seq=after_seq, before_seq=before_seq, limit=limit, last=last)
        return await self._storage.read(
            self._scope,
            after_seq=after_seq,
            before_seq=before_seq,
            threads=threads,
            limit=limit,
            last=last,
        )

    async def subscribe(
        self, *, after_seq: int = 0, threads: Collection[ThreadId] | None = None
    ) -> AsyncIterator[Envelope]:
        """Yield envelopes after ``after_seq``: the stored ones, then new ones as they commit.

        Replay and live delivery are the same stream, so nothing falls between them. Reading
        the log is untraced, so a subscription that polls storage makes no trace per poll
        (ADR-0046); what the subscriber does with each envelope is traced as usual.
        """
        stream = self._storage.subscribe(self._scope, after_seq=after_seq)
        async with contextlib.aclosing(stream) as envelopes:
            while True:
                with untraced():
                    envelope = await anext(envelopes, None)
                if envelope is None:
                    return
                if delivered_to(envelope, threads):
                    yield envelope

    async def change_notes(
        self,
        *,
        after_seq: int,
        before_seq: int | None = None,
        focus: Collection[ArtifactId] | None = None,
        viewer: Actor | None = None,
    ) -> list[Note]:
        """Return notes about what others did in the window ``after_seq < seq < before_seq``.

        Args:
            after_seq: Only consider envelopes with a greater ``seq``.
            before_seq: Only consider envelopes with a lesser ``seq``; ``None`` reads to the head.
            focus: The artifacts the viewer follows; ``None`` means all.
            viewer: Who the notes are for; defaults to this handle's actor.
        """
        envelopes = await self._storage.read(
            self._scope, after_seq=after_seq, before_seq=before_seq
        )
        return change_notes(envelopes, viewer=viewer or self._actor, focus=focus)

    async def cursor(self, name: str) -> int:
        """Return how far a named consumer of the log has got: the ``seq`` it saved, or 0.

        A consumer, such as a feedback mirror, saves its cursor with :meth:`save_cursor` and
        carries on after it when it starts again.
        """
        return await self._storage.cursor(self._scope, name)

    async def save_cursor(self, name: str, seq: int) -> None:
        """Save how far a named consumer of the log has got: it is done with ``seq``.

        A cursor only moves forward: saving a ``seq`` below the saved one leaves it, so a
        consumer that runs in several processes, each at its own pace, cannot move it back.
        """
        await self._storage.save_cursor(self._scope, name, seq)

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
            try:
                await asyncio.gather(renewal, return_exceptions=True)
            finally:
                await self._storage.release_lease(self._scope, key, holder)

    async def _renew(self, key: str, holder: str, ttl: timedelta) -> None:
        # Renewing is bookkeeping, not part of the turn that holds the thread.
        with untraced():
            while True:
                await asyncio.sleep(ttl.total_seconds() / 3)
                try:
                    await self._storage.acquire_lease(self._scope, key, holder, ttl)
                except Exception:
                    logger.exception("renewing the claim %s failed; retrying", key)


def _check_page(
    *, after_seq: int, before_seq: int | None, limit: int | None, last: int | None
) -> None:
    """Refuse a read of the log that gives both ``limit`` and ``last``, or a negative number."""
    if limit is not None and last is not None:
        raise ValidationFailed("give limit or last, not both", [])
    given = {"after_seq": after_seq, "before_seq": before_seq, "limit": limit, "last": last}
    for name, value in given.items():
        if value is not None and value < 0:
            raise ValidationFailed(f"{name} cannot be negative", [])


def _traced(result: CommitResult) -> CommitResult:
    """Stamp the current trace on the revisions a result appends (ADR-0033)."""
    trace_id = current_trace_id()
    if trace_id is None or not result.revisions:
        return result
    revisions = tuple(r.model_copy(update={"trace_id": trace_id}) for r in result.revisions)
    return dataclasses.replace(result, revisions=revisions)


def _merge(state: State, loaded: State) -> State:
    return State(
        artifacts={**state.artifacts, **loaded.artifacts},
        proposals={**state.proposals, **loaded.proposals},
        threads={**state.threads, **loaded.threads},
        runs={**state.runs, **loaded.runs},
        messages={**state.messages, **loaded.messages},
    )
