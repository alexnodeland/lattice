"""Workspaces: tenant-scoped handles over artifacts, threads and the log (ADR-0011).

Every read and write goes through a :class:`Workspace`, each of whose methods asks the
application's ``authorize`` hook first, with the action it takes (ADR-0056). Every write goes
through :meth:`Workspace.commit` or :meth:`Workspace.record`, which run core's rules inside one
storage transaction (ADR-0002, ADR-0018). Each commit is traced as an ``artifactr.commit {type}``
span, and what commits and facts do is counted in artifactr's metrics. Every envelope records
the W3C trace context of the span it was committed in, and every revision that span's trace
(ADR-0033).
"""

import asyncio
import contextlib
import dataclasses
import functools
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
from typing import Final, Literal, cast, overload

from opentelemetry.metrics import MeterProvider
from opentelemetry.trace import StatusCode, TracerProvider
from pydantic import BaseModel, ConfigDict

from artifactr.core import (
    Actor,
    Applied,
    ArchiveArtifact,
    Artifact,
    ArtifactId,
    ArtifactTarget,
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
    MessageKind,
    MessageTarget,
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
    ThreadTarget,
    TurnTarget,
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
from artifactr.core.visibility import (
    Hides,
    Visibility,
    hides_nothing,
    seen,
    seen_artifact,
    seen_proposal,
    seen_revision,
    seen_thread,
)
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
from lattice_core.text import holds_nul

logger = logging.getLogger("artifactr.workspace")

ACTIONS: Final = frozenset(
    {
        "artifactr:open",
        "artifactr:read_workspaces",
        # commands, by their type
        "artifactr:create_artifact",
        "artifactr:edit_artifact",
        "artifactr:archive_artifact",
        "artifactr:propose_change",
        "artifactr:respond_to_proposal",
        "artifactr:create_thread",
        "artifactr:post_message",
        "artifactr:set_focus",
        "artifactr:set_thread_mode",
        "artifactr:answer_deferred",
        "artifactr:give_feedback",
        "artifactr:stop_run",
        # the agent's runs, and consumers of the log
        "artifactr:record",
        "artifactr:claim_thread",
        "artifactr:save_cursor",
        # reads
        "artifactr:read_artifacts",
        "artifactr:read_threads",
        "artifactr:read_proposals",
        "artifactr:read_runs",
        "artifactr:read_history",
        "artifactr:read_events",
        "artifactr:read_cursors",
    }
)
"""Every action a :class:`Workspace` asks ``authorize`` about: the complete catalog.

An action is ``artifactr:`` and a name. A command's is its ``type``, a read's is ``read_`` and
what it reads, and opening a workspace is ``artifactr:open``. ``artifactr:read_workspaces``,
listing a tenant's workspaces, is the one asked with no workspace.
"""


MAX_COUNT: Final = 2**63 - 1
"""The largest ``seq`` or count a read takes: what PostgreSQL's ``bigint`` holds."""


class Access(BaseModel):
    """What an actor is about to do in a workspace, as ``authorize`` hears it."""

    model_config = ConfigDict(frozen=True)

    action: str
    """One of :data:`ACTIONS`."""

    thread_id: ThreadId | None = None
    """The thread it is about, when it names one."""

    artifact_id: ArtifactId | None = None
    """The artifact it is about, when it names one."""


Authorize = Callable[[TenantId, WorkspaceId | None, Actor, Access], Awaitable[bool]]
"""Decides whether an actor may take an action in a workspace of its tenant.

:class:`Workspaces` holds it, and every :class:`Workspace` it opens asks it in each method,
before anything is read or written: so every REST request, WebSocket command, MCP tool call
and in-process call is checked alike. A refusal raises :class:`~artifactr.core.Forbidden`.
The workspace is ``None`` only for listing a tenant's workspaces, which spans the tenant.
"""

Hidden = Callable[[TenantId, WorkspaceId, Actor], Awaitable[Hides]]
"""The threads and artifacts an actor may not see in a workspace (lattice RFC-0001).

:class:`Workspaces` holds it, and every read leaves out what it returns: a listing skips a
hidden item, a single read of one raises :class:`~artifactr.core.NotFound` as a missing one
does, and the log drops the envelopes about one. An open subscription asks again every
``hidden_refresh``. It answers with a :class:`~artifactr.core.Visibility`, or any object with
its ``threads`` and ``artifacts``.
"""

OnOpen = Callable[[TenantId, WorkspaceId], Awaitable[None]]
"""Called each time :meth:`Workspaces.open` opens a workspace, after ``authorize`` allows it.

It starts a workspace's background work, such as a feedback mirror, so it must be idempotent:
a permission check has no side effects.
"""


_OPEN: Final = Access(action="artifactr:open")

_NOTHING: Final = Visibility()

_WORKSPACES_PAGE: Final = 500
"""How many workspace ids :meth:`Workspaces.list` reads from storage at a time, whatever its
``limit``: a database can't take any number as a page's size."""


class ThreadBusy(InvalidState):
    """Another run holds the thread."""


class Workspaces:
    """Opens scoped :class:`Workspace` handles over one storage.

    Args:
        storage: Where workspaces are kept.
        types: The artifact types this application accepts. Others are rejected even if they
            are registered, so clients cannot create arbitrary types. ``None`` accepts every
            registered type.
        authorize: Whether an actor may take an action, asked by every handle in each of its
            methods; allows everything if omitted.
        on_open: Called each time a workspace is opened, once ``authorize`` allows it.
        hidden: The threads and artifacts an actor may not see, which every read leaves out;
            hides nothing if omitted.
        hidden_refresh: How often an open subscription asks ``hidden`` again.
        tracer_provider: Where commit spans go. Defaults to the global tracer provider.
        meter_provider: Where artifactr's metrics go. Defaults to the global meter provider.
    """

    def __init__(
        self,
        storage: Storage,
        *,
        types: Iterable[type[Artifact]] | None = None,
        authorize: Authorize | None = None,
        on_open: OnOpen | None = None,
        hidden: Hidden | None = None,
        hidden_refresh: timedelta = timedelta(seconds=30),
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None = None,
    ) -> None:
        self._context = _Context(
            storage=storage,
            kinds=None if types is None else frozenset(t.kind for t in types),
            authorize=authorize,
            hidden=hidden,
            hidden_refresh=hidden_refresh.total_seconds(),
            telemetry=Telemetry(tracer_provider=tracer_provider, meter_provider=meter_provider),
        )
        self._on_open = on_open

    async def open(
        self, tenant_id: TenantId, workspace_id: WorkspaceId, *, actor: Actor
    ) -> "Workspace":
        """Return a handle on a tenant's workspace, acting as ``actor``.

        This is the only place a tenant id enters; nothing on the handle can reach another
        tenant. Opening asks ``authorize`` for ``artifactr:open``, then calls ``on_open``.

        Raises:
            Forbidden: If ``authorize`` refuses the actor this workspace.
        """
        _check_text(tenant_id, workspace_id, actor)
        workspace = Workspace(self._context, Scope(tenant_id, workspace_id), actor)
        await workspace.check(_OPEN)
        if self._on_open is not None:
            await self._on_open(tenant_id, workspace_id)
        return workspace

    # Last in the class: below it, ``list`` in an annotation would name this method.
    async def list(
        self,
        tenant_id: TenantId,
        *,
        actor: Actor,
        after: WorkspaceId | None = None,
        limit: int = 100,
    ) -> list[WorkspaceId]:
        """Return a page of the tenant's workspaces that ``actor`` may open, ordered by id.

        A workspace is listed once its log has an event. Listing spans the tenant, so it asks
        ``authorize`` for ``artifactr:read_workspaces`` with no workspace, then for
        ``artifactr:open`` in each workspace it finds, and leaves out those refused (ADR-0058).
        It opens none of them, so ``on_open`` is not called. A page is full unless the list
        has ended; pass its last id as ``after`` for the next.

        Raises:
            Forbidden: If ``authorize`` refuses the actor the list.
            ValidationFailed: If ``limit`` is below 1.
        """
        _check_text(tenant_id, actor, after)
        context = self._context
        await context.check(tenant_id, None, actor, Access(action="artifactr:read_workspaces"))
        if limit < 1:
            raise ValidationFailed("limit must be at least 1", [])
        found: list[WorkspaceId] = []
        while len(found) < limit:
            wanted = min(limit - len(found), _WORKSPACES_PAGE)
            page = await context.storage.workspaces(tenant_id, after=after, limit=wanted)
            found += [w for w in page if await context.allows(tenant_id, w, actor, _OPEN)]
            if len(page) < wanted:
                break
            after = page[-1]
        return found


@dataclasses.dataclass(frozen=True)
class _Context:
    """What every handle of one :class:`Workspaces` shares."""

    storage: Storage
    kinds: frozenset[str] | None
    authorize: Authorize | None
    hidden: Hidden | None
    hidden_refresh: float
    telemetry: Telemetry

    async def allows(
        self, tenant_id: TenantId, workspace_id: WorkspaceId | None, actor: Actor, access: Access
    ) -> bool:
        """Whether ``authorize`` lets an actor take an action; true without a hook."""
        return self.authorize is None or await self.authorize(
            tenant_id, workspace_id, actor, access
        )

    async def check(
        self, tenant_id: TenantId, workspace_id: WorkspaceId | None, actor: Actor, access: Access
    ) -> None:
        """Ask ``authorize`` whether an actor may take an action, as every check does.

        Raises:
            Forbidden: If ``authorize`` refuses it.
        """
        if not await self.allows(tenant_id, workspace_id, actor, access):
            where = "tenant" if workspace_id is None else "workspace"
            raise Forbidden(f"{access.action} is refused in this {where}")


class Workspace:
    """A handle on one tenant's workspace, bound to the actor it acts as.

    Create handles with :meth:`Workspaces.open`, and derive handles for other actors (such as
    the agent) with :meth:`as_actor`. Each method asks the ``authorize`` hook first, as the
    handle's actor, with the action it takes; a refusal raises
    :class:`~artifactr.core.Forbidden`.
    """

    def __init__(self, context: _Context, scope: Scope, actor: Actor) -> None:
        self._context = context
        self._storage = context.storage
        self._scope = scope
        self._actor = actor
        self._kinds = context.kinds
        self._telemetry = context.telemetry
        self._tenancy = {TENANT_ID: scope.tenant_id, WORKSPACE_ID: scope.workspace_id}
        self._hides: tuple[float, Hides] | None = None

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
        """Return a handle on the same workspace that acts as ``actor``, checked as it."""
        _check_text(actor)
        return Workspace(self._context, self._scope, actor)

    async def check(self, access: Access) -> None:
        """Ask ``authorize`` whether this handle's actor may take an action here.

        Every method asks it first. A surface asks it itself only for what it does beside the
        workspace, as the runner does to stop a run.

        Raises:
            NotFound: If the access names a thread or artifact hidden from the actor, as if it
                were missing, so ids can't be probed.
            Forbidden: If ``authorize`` refuses it.
        """
        if access.thread_id is not None or access.artifact_id is not None:
            _not_hidden(access, await self.hidden())
        await self._authorize(access)

    async def _read(self, access: Access) -> Hides:
        """Check a read as :meth:`check` does, and return what it leaves out."""
        hidden = await self.hidden()
        _not_hidden(access, hidden)
        await self._authorize(access)
        return hidden

    async def _read_of(self, access: Access) -> Hides | None:
        """Check a read of what a thread holds, or None if the thread is hidden.

        A read of a hidden thread's runs or history answers as for a thread that doesn't exist,
        which has none: it is asked of the workspace, and finds nothing.
        """
        hidden = await self.hidden()
        if access.thread_id in hidden.threads:
            await self._authorize(access.model_copy(update={"thread_id": None}))
            return None
        await self._authorize(access)
        return hidden

    async def _authorize(self, access: Access) -> None:
        scope = self._scope
        await self._context.check(scope.tenant_id, scope.workspace_id, self._actor, access)

    async def hidden(self) -> Hides:
        """What this handle's actor may not see here: nothing without a ``hidden`` hook.

        The handle asks the hook once every ``hidden_refresh`` at most, so a request asks it
        once; a handle from :meth:`as_actor` asks afresh.
        """
        hook = self._context.hidden
        if hook is None:
            return _NOTHING
        now = time.monotonic()
        if self._hides is None or now - self._hides[0] >= self._context.hidden_refresh:
            hides = await hook(self._scope.tenant_id, self._scope.workspace_id, self._actor)
            self._hides = (now, hides)
        return self._hides[1]

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
        *,
        cursor: tuple[str, int] | None = None,
        claim: tuple[ThreadId, str] | None = None,
    ) -> Recorded: ...

    async def commit(
        self,
        command: Command,
        *,
        cursor: tuple[str, int] | None = None,
        claim: tuple[ThreadId, str] | None = None,
    ) -> Outcome:
        """Submit a command.

        Args:
            command: The command.
            cursor: A named cursor, ``(name, seq)``, to save in the same transaction, as with
                :meth:`save_cursor`: it moves only if the command is applied.
            claim: A thread's claim, ``(thread_id, holder)``, that fences the command: it is
                applied only while ``holder`` has the thread (:meth:`claim_thread`).

        Returns:
            What the command did, with the ``seq`` of the last event it appended.

        Raises:
            Rejection: If the command cannot be applied; ThreadBusy, a rejection too, if
                ``claim`` is given and its holder no longer has the thread.
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
                _check_text(command, cursor, claim)
                await self.check(_access(command))
                command = await self._check_target(command)
                self._check_kind(command)
                outcome = await self._transact(
                    command,
                    lambda state: commit(command, state, actor=self._actor),
                    cursor=cursor,
                    claim=claim,
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

    async def record(
        self,
        fact: Fact,
        *,
        history: bytes | None = None,
        cursor: tuple[str, int] | None = None,
        claim: tuple[ThreadId, str] | None = None,
    ) -> Recorded:
        """Record a fact about an agent run, or an application event.

        Args:
            fact: The fact to record.
            history: Serialized model messages to append to the fact's thread history in the
                same transaction, typically with ``RunPaused`` or ``RunEnded``.
            cursor: A named cursor, ``(name, seq)``, to save in the same transaction, as with
                :meth:`save_cursor`: it moves only if the fact is recorded.
            claim: A thread's claim, ``(thread_id, holder)``, that fences the fact: it is
                recorded only while ``holder`` has the thread (:meth:`claim_thread`).

        Raises:
            ThreadBusy: If ``claim`` is given and its holder no longer has the thread.
        """
        _check_text(fact, cursor, claim)
        await self.check(Access(action="artifactr:record", thread_id=fact.thread_id))
        outcome = await self._transact(
            fact,
            lambda state: record(fact, state, actor=self._actor),
            history=(fact.thread_id, history) if history is not None and fact.thread_id else None,
            cursor=cursor,
            claim=claim,
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
        thread = await self._storage.thread(self._scope, command.thread_id)
        assert thread is not None, "a thread is there once it is created"
        return thread

    async def post_message(
        self,
        thread_id: ThreadId,
        content: str,
        *,
        message_id: MessageId | None = None,
        kind: MessageKind = "message",
    ) -> Recorded:
        """Post a message, or a notice, in a thread as this handle's actor.

        Args:
            thread_id: The thread to post in.
            content: What the message says.
            message_id: The message's id; a new one when omitted. An id already used in the
                workspace is refused with :class:`~artifactr.core.InvalidState`.
            kind: ``notice`` for a notice, which is for people and starts no run (ADR-0051).
        """
        message = PostMessage(
            thread_id=thread_id,
            content=content,
            message_id=message_id or new_message_id(),
            kind=kind,
        )
        return await self.commit(message)

    async def _transact(
        self,
        item: Command | Fact,
        decide: Callable[[State], CommitResult],
        *,
        history: tuple[ThreadId, bytes] | None = None,
        cursor: tuple[str, int] | None = None,
        claim: tuple[ThreadId, str] | None = None,
    ) -> Outcome:
        async with self._storage.transaction(self._scope) as transaction:
            if claim is not None and not await transaction.holds_lease(
                _thread_key(claim[0]), claim[1]
            ):
                raise ThreadBusy(f"thread {claim[0]} is held by another claim now")
            state = State()
            while missing := needs(item, actor=self._actor, state=state):
                state = _merge(state, await transaction.load(missing))
            result = _traced(decide(state))
            envelopes = await transaction.save(
                result, actor=self._actor, traceparent=current_traceparent()
            )
            if history is not None:
                await transaction.append_history(*history)
            if cursor is not None:
                await transaction.save_cursor(*cursor)
        record_events(self._telemetry, result.events, actor=self._actor, scope=self._tenancy)
        if not envelopes:
            return result.outcome
        return result.outcome.model_copy(update={"seq": envelopes[-1].seq})

    async def _check_target(self, command: Command) -> Command:
        """Ask about what a command acts on beyond what it names, and keep what it can't see.

        Answering a proposal acts on its artifact, and answering a paused run, or giving
        feedback on a turn, on its run's thread, so each is asked about that item too: refused,
        or missing, as the proposal or run itself, if the item is hidden. A focus may name no
        hidden artifact, and keeps those the actor can't see, which it can't have chosen to drop.
        """
        action = f"artifactr:{command.type}"
        match command:
            case RespondToProposal(proposal_id=proposal_id):
                proposal = await self._storage.proposal(self._scope, proposal_id)
                if proposal is not None:
                    access = Access(action=action, artifact_id=proposal.artifact_id)
                    await self._ask_about(access, NotFound("proposal", proposal_id))
            case (
                AnswerDeferred(run_id=run_id)
                | GiveFeedback(target=TurnTarget(run_id=run_id))
                | GiveFeedback(target=MessageTarget(run_id=str() as run_id))
            ):
                run = await self._storage.run(self._scope, run_id)
                if run is not None:
                    access = Access(action=action, thread_id=run.thread_id)
                    await self._ask_about(access, NotFound("run", run_id))
            case SetFocus(thread_id=thread_id, artifact_ids=artifact_ids):
                hidden = await self.hidden()
                for artifact_id in artifact_ids:
                    _not_hidden(Access(action=action, artifact_id=artifact_id), hidden)
                thread = await self._storage.thread(self._scope, thread_id)
                kept = (
                    ()
                    if thread is None
                    else tuple(a for a in thread.focus if a in hidden.artifacts)
                )
                if kept:
                    return command.model_copy(update={"artifact_ids": (*artifact_ids, *kept)})
            case _:
                pass
        return command

    async def _ask_about(self, access: Access, missing: NotFound) -> None:
        """Ask about an item a command acts on: ``missing`` if it is hidden."""
        try:
            _not_hidden(access, await self.hidden())
        except NotFound:
            raise missing from None
        await self._authorize(access)

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
        _check_text(artifact_id)
        missing = NotFound(getattr(artifact_type, "kind", "artifact"), artifact_id)
        access = Access(action="artifactr:read_artifacts", artifact_id=artifact_id)
        try:
            hidden = await self._read(access)
        except NotFound:
            raise missing from None  # hidden, and named as a missing one of its type is
        artifact = await self._storage.artifact(self._scope, artifact_id)
        if artifact is None or not isinstance(artifact.data, artifact_type):
            raise missing
        return seen_artifact(cast("Versioned[A]", artifact), hidden)

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
        _check_text(kind)
        hidden = await self._read(Access(action="artifactr:read_artifacts"))
        artifacts = await self._storage.artifacts(
            self._scope, kind=kind, include_archived=include_archived
        )
        return [
            seen_artifact(cast("Versioned[A]", artifact), hidden)
            for artifact in artifacts
            if isinstance(artifact.data, artifact_type) and artifact.id not in hidden.artifacts
        ]

    async def revisions(self, artifact_id: ArtifactId) -> list[Revision]:
        """Return an artifact's revisions, oldest first.

        Raises:
            NotFound: If there is no such artifact: every artifact has a revision.
        """
        _check_text(artifact_id)
        access = Access(action="artifactr:read_artifacts", artifact_id=artifact_id)
        hidden = await self._read(access)
        revisions = await self._storage.revisions(self._scope, artifact_id)
        if not revisions:
            raise NotFound("artifact", artifact_id)
        return [seen_revision(revision, hidden) for revision in revisions]

    async def thread(self, thread_id: ThreadId) -> Thread:
        """Return a thread.

        Raises:
            NotFound: If there is no such thread.
        """
        _check_text(thread_id)
        hidden = await self._read(Access(action="artifactr:read_threads", thread_id=thread_id))
        thread = await self._storage.thread(self._scope, thread_id)
        if thread is None:
            raise NotFound("thread", thread_id)
        return seen_thread(thread, hidden)

    async def threads(self) -> list[Thread]:
        """Return every thread, oldest first."""
        hidden = await self._read(Access(action="artifactr:read_threads"))
        return [
            seen_thread(thread, hidden)
            for thread in await self._storage.threads(self._scope)
            if thread.id not in hidden.threads
        ]

    async def proposal(self, proposal_id: ProposalId) -> Proposal:
        """Return a proposal.

        Raises:
            NotFound: If there is no such proposal.
        """
        _check_text(proposal_id)
        hidden = await self._read(Access(action="artifactr:read_proposals"))
        proposal = await self._storage.proposal(self._scope, proposal_id)
        shown = None if proposal is None else seen_proposal(proposal, hidden)
        if shown is None:
            raise NotFound("proposal", proposal_id)
        return shown

    async def proposals(
        self, *, status: Literal["pending", "accepted", "rejected"] | None = "pending"
    ) -> list[Proposal]:
        """Return proposals with a status (pending by default; None for all), oldest first."""
        hidden = await self._read(Access(action="artifactr:read_proposals"))
        proposals = await self._storage.proposals(self._scope, status=status)
        return [shown for p in proposals if (shown := seen_proposal(p, hidden)) is not None]

    async def run(self, run_id: RunId) -> Run:
        """Return a run.

        Raises:
            NotFound: If there is no such run.
        """
        _check_text(run_id)
        hidden = await self._read(Access(action="artifactr:read_runs"))
        run = await self._storage.run(self._scope, run_id)
        if run is None or run.thread_id in hidden.threads:
            raise NotFound("run", run_id)
        return run

    async def runs(
        self, *, thread_id: ThreadId | None = None, status: RunStatus | None = None
    ) -> list[Run]:
        """Return runs, optionally of one thread and with one status, oldest first.

        A hidden thread has none, as one that doesn't exist has none.
        """
        _check_text(thread_id)
        hidden = await self._read_of(Access(action="artifactr:read_runs", thread_id=thread_id))
        if hidden is None:
            return []
        runs = await self._storage.runs(self._scope, thread_id=thread_id, status=status)
        return [run for run in runs if run.thread_id not in hidden.threads]

    async def history(self, thread_id: ThreadId) -> Sequence[HistoryChunk]:
        """Return a thread's history: serialized model messages, one chunk per run segment.

        A hidden thread has none, as one that doesn't exist has none.
        """
        _check_text(thread_id)
        access = Access(action="artifactr:read_history", thread_id=thread_id)
        if await self._read_of(access) is None:
            return []
        return await self._storage.history(self._scope, thread_id)

    # ─── the log ──────────────────────────────────────────────────────────────

    async def head_seq(self) -> int:
        """Return the log's latest ``seq``, or 0 if it is empty."""
        await self.check(Access(action="artifactr:read_events"))
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
            ValidationFailed: If both ``limit`` and ``last`` are given, or a number is negative
                or more than storage holds.
        """
        _check_text(threads)
        hidden = await self._read(Access(action="artifactr:read_events"))
        _check_page(after_seq=after_seq, before_seq=before_seq, limit=limit, last=last)
        window = functools.partial(self._storage.read, self._scope, threads=threads)
        if hides_nothing(hidden):
            return await window(after_seq=after_seq, before_seq=before_seq, limit=limit, last=last)
        if limit is None and last is None:
            return _seen(await window(after_seq=after_seq, before_seq=before_seq), hidden)
        # Envelopes left out don't count: read on until the page is full or the window ends,
        # so a page is short only at the end, whatever was hidden.
        found: list[Envelope] = []
        if limit is not None:
            while (missing := limit - len(found)) > 0:
                page = await window(after_seq=after_seq, before_seq=before_seq, limit=missing)
                found += _seen(page, hidden)
                if len(page) < missing:
                    break
                after_seq = page[-1].seq
            return found
        assert last is not None, "limit or last is given"
        while (missing := last - len(found)) > 0:
            page = await window(after_seq=after_seq, before_seq=before_seq, last=missing)
            found = _seen(page, hidden) + found
            if len(page) < missing:
                break
            before_seq = page[0].seq
        return found

    async def subscribe(
        self, *, after_seq: int = 0, threads: Collection[ThreadId] | None = None
    ) -> AsyncIterator[Envelope]:
        """Yield envelopes after ``after_seq``: the stored ones, then new ones as they commit.

        Replay and live delivery are the same stream, so nothing falls between them. Reading
        the log is untraced, so a subscription that polls storage makes no trace per poll
        (ADR-0046); what the subscriber does with each envelope is traced as usual.

        It leaves out what ``hidden`` hides from the actor, asking it again every
        ``hidden_refresh``, so an item restricted while it is open is left out from then on.
        """
        _check_text(threads)
        hidden = await self._read(Access(action="artifactr:read_events"))
        stream = self._storage.subscribe(self._scope, after_seq=after_seq)
        async with contextlib.aclosing(stream) as envelopes:
            while True:
                with untraced():
                    envelope = await anext(envelopes, None)
                    hidden = await self.hidden()  # asked again every hidden_refresh
                if envelope is None:
                    return
                shown = seen(envelope, hidden)
                if shown is not None and delivered_to(shown, threads):
                    yield shown

    async def change_notes(
        self,
        *,
        after_seq: int,
        before_seq: int | None = None,
        focus: Collection[ArtifactId] | None = None,
        viewer: Actor | None = None,
        notices: bool = False,
    ) -> list[Note]:
        """Return notes about what others did in the window ``after_seq < seq < before_seq``.

        Args:
            after_seq: Only consider envelopes with a greater ``seq``.
            before_seq: Only consider envelopes with a lesser ``seq``; ``None`` reads to the head.
            focus: The artifacts the viewer follows; ``None`` means all.
            viewer: Who the notes are for; defaults to this handle's actor.
            notices: Include the notices others posted in the viewer's thread, when the viewer
                is a thread's agent.
        """
        _check_text(focus, viewer)
        hidden = await self._read(Access(action="artifactr:read_events"))
        envelopes = await self._storage.read(
            self._scope, after_seq=after_seq, before_seq=before_seq
        )
        return change_notes(
            _seen(envelopes, hidden), viewer=viewer or self._actor, focus=focus, notices=notices
        )

    async def cursor(self, name: str) -> int:
        """Return how far a named consumer of the log has got: the ``seq`` it saved, or 0.

        A consumer, such as a feedback mirror, saves its cursor with :meth:`save_cursor` and
        carries on after it when it starts again.
        """
        _check_text(name)
        await self.check(Access(action="artifactr:read_cursors"))
        return await self._storage.cursor(self._scope, name)

    async def save_cursor(self, name: str, seq: int) -> None:
        """Save how far a named consumer of the log has got: it is done with ``seq``.

        A cursor only moves forward: saving a ``seq`` below the saved one leaves it, so a
        consumer that runs in several processes, each at its own pace, cannot move it back.
        """
        _check_text(name)
        await self.check(Access(action="artifactr:save_cursor"))
        await self._storage.save_cursor(self._scope, name, seq)

    # ─── runs ─────────────────────────────────────────────────────────────────

    @contextlib.asynccontextmanager
    async def claim_thread(
        self, thread_id: ThreadId, *, holder: str, ttl: timedelta = timedelta(seconds=30)
    ) -> AsyncGenerator[asyncio.Event]:
        """Hold a thread exclusively, renewing the claim until the block exits.

        One run is active per thread. The claim is a lease in storage, so it holds across
        processes and lapses by itself if the holder dies. A call cancelled, or failing, as it
        claims releases the lease, which storage may have granted all the same.

        Yields:
            An event set once the claim is lost: it lapsed, a whole ``ttl`` after its last
            renewal began, even while a renewal hangs, or a renewal found that another holder
            has the thread. The claim is never renewed after that, even if storage would allow
            it. Its lease is released only when the block exits, so exit promptly once the event
            is set.

        Raises:
            ThreadBusy: If another holder has the thread.
        """
        _check_text(thread_id, holder)
        await self.check(Access(action="artifactr:claim_thread", thread_id=thread_id))
        key = _thread_key(thread_id)
        lapses = asyncio.get_running_loop().time() + ttl.total_seconds()
        try:
            acquired = await self._storage.acquire_lease(self._scope, key, holder, ttl)
        except BaseException:
            # A call cut short may still have taken the lease (Storage): no task would release it.
            await self._storage.release_lease(self._scope, key, holder)
            raise
        if not acquired:
            raise ThreadBusy(f"thread {thread_id} is busy with another run")
        lost = asyncio.Event()
        renewal = asyncio.create_task(self._renew(key, holder, ttl, lapses, lost))
        try:
            yield lost
        finally:
            renewal.cancel()
            try:
                await asyncio.gather(renewal, return_exceptions=True)
            finally:
                await self._storage.release_lease(self._scope, key, holder)

    async def _renew(
        self, key: str, holder: str, ttl: timedelta, lapses: float, lost: asyncio.Event
    ) -> None:
        # Renewing is bookkeeping, not part of the turn that holds the thread. A timer on the
        # loop's monotonic clock marks the claim lost when it lapses, at ``lapses``, a ttl after
        # its last renewal began, whatever storage is doing.
        loop = asyncio.get_running_loop()
        with untraced():
            lapse = loop.call_at(lapses, _lose, key, lost)
            try:
                while True:
                    await asyncio.sleep(ttl.total_seconds() / 3)
                    if lost.is_set():
                        return
                    renewing = loop.time()
                    try:
                        kept = await self._storage.acquire_lease(self._scope, key, holder, ttl)
                    except Exception:
                        logger.exception("renewing the claim %s failed; retrying", key)
                        continue
                    if lost.is_set():
                        return  # it lapsed while the renewal was in flight
                    if not kept:
                        _lose(key, lost)  # another holder has the thread
                        return
                    lapse.cancel()
                    lapse = loop.call_at(renewing + ttl.total_seconds(), _lose, key, lost)
            finally:
                lapse.cancel()


def _thread_key(thread_id: ThreadId) -> str:
    """The key of a thread's claim, as a lease."""
    return f"thread:{thread_id}"


def _lose(key: str, lost: asyncio.Event) -> None:
    """Mark a thread claim lost: it lapsed, or another holder has the thread."""
    logger.warning("the claim %s lapsed, so it is lost", key)
    lost.set()


def _access(command: Command) -> Access:
    """What a command asks ``authorize`` for: its type, and the thread and artifact it names."""
    action = f"artifactr:{command.type}"
    match command:
        case ProposeChange(change=change):
            return Access(action=action, thread_id=change.thread_id, artifact_id=change.artifact_id)
        case CreateArtifact() | EditArtifact() | ArchiveArtifact():
            return Access(
                action=action, thread_id=command.thread_id, artifact_id=command.artifact_id
            )
        case PostMessage() | SetFocus() | SetThreadMode():
            return Access(action=action, thread_id=command.thread_id)
        case GiveFeedback(target=ArtifactTarget(artifact_id=artifact_id)):
            return Access(action=action, artifact_id=artifact_id)
        case GiveFeedback(
            target=ThreadTarget(thread_id=thread_id) | MessageTarget(thread_id=thread_id)
        ):
            return Access(action=action, thread_id=thread_id)
        case _:
            return Access(action=action)


def _check_text(*values: object) -> None:
    """Refuse a NUL character in any string ``values`` hold, as models, mappings or collections.

    PostgreSQL's text can't hold one, so every storage refuses it alike, before ``authorize``
    hears it (artifactr ADR-0061, reflexr ADR-0060).

    Raises:
        ValidationFailed: If a string holds a NUL character.
    """
    if holds_nul(*values):
        raise ValidationFailed("text cannot hold a NUL character", [])


def _not_hidden(access: Access, hidden: Hides) -> None:
    """Refuse an access to a hidden thread or artifact as if it were missing.

    Raises:
        NotFound: If the access names a thread or artifact in ``hidden``.
    """
    if access.thread_id is not None and access.thread_id in hidden.threads:
        raise NotFound("thread", access.thread_id)
    if access.artifact_id is not None and access.artifact_id in hidden.artifacts:
        raise NotFound("artifact", access.artifact_id)


def _seen(envelopes: Iterable[Envelope], hidden: Hides) -> list[Envelope]:
    """Envelopes as an actor who may not see ``hidden`` reads them."""
    return [shown for envelope in envelopes if (shown := seen(envelope, hidden)) is not None]


def _check_page(
    *, after_seq: int, before_seq: int | None, limit: int | None, last: int | None
) -> None:
    """Refuse a read of the log that gives both ``limit`` and ``last``, or a number out of range."""
    if limit is not None and last is not None:
        raise ValidationFailed("give limit or last, not both", [])
    given = {"after_seq": after_seq, "before_seq": before_seq, "limit": limit, "last": last}
    for name, value in given.items():
        _check_count(name, value)


def _check_count(name: str, value: int | None) -> None:
    """Refuse a ``seq`` or a count that is negative, or more than storage can hold."""
    if value is not None and value < 0:
        raise ValidationFailed(f"{name} cannot be negative", [])
    if value is not None and value > MAX_COUNT:
        raise ValidationFailed(f"{name} cannot be more than {MAX_COUNT}", [])


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
