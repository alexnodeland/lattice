"""SQL storage: workspaces in a database, through SQLAlchemy's asyncio extension.

It implements the full :class:`~artifactr.workspace.Storage` protocol with the same code on
PostgreSQL and SQLite. A transaction locks its workspace's row before it reads anything, so
transactions on one workspace run one at a time, across processes; ``seq`` is assigned under
that lock. Subscriptions poll the log, and wake at once for commits made through the same
:class:`SqlStorage`.
"""

import asyncio
import contextlib
import uuid
from collections.abc import AsyncGenerator, Callable, Collection, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import ColumnElement, Select, delete, insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from artifactr.core import (
    WORKSPACE_SCOPED,
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
    load_versioned,
    scope_of,
)
from artifactr.core.actors import Actor
from artifactr.sql.tables import (
    ArtifactRow,
    CursorRow,
    EntityRow,
    EventRow,
    HistoryRow,
    LeaseRow,
    MessageRow,
    ProposalRow,
    RevisionRow,
    RunRow,
    ScopedRow,
    ThreadRow,
    WorkspaceRow,
)
from artifactr.workspace import HistoryChunk, Scope

Clock = Callable[[], datetime]
"""Returns the current time; injectable so tests control expiry."""

_PAGE = 500
"""How many envelopes a subscription reads at a time."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


class _Transaction:
    def __init__(
        self, session: AsyncSession, scope: Scope, workspace: WorkspaceRow, clock: Clock
    ) -> None:
        self._session = session
        self._scope = scope
        self._workspace = workspace
        self._clock = clock
        self._history: list[tuple[ThreadId, bytes]] = []

    async def load(self, needs: Needs) -> State:
        # The session flushes earlier saves before it queries, so later loads see them.
        return State(
            artifacts=await self._load(ArtifactRow, needs.artifacts, _versioned),
            proposals=await self._load(ProposalRow, needs.proposals, _proposal),
            threads=await self._load(ThreadRow, needs.threads, _thread),
            runs=await self._load(RunRow, needs.runs, _run),
            messages=await self._used(needs.messages),
        )

    async def _used(self, message_ids: frozenset[MessageId]) -> dict[MessageId, bool]:
        if not message_ids:
            return {}
        rows = await self._session.scalars(
            _scoped(MessageRow, self._scope).where(MessageRow.id.in_(message_ids))
        )
        used = {row.id for row in rows}
        return {i: i in used for i in message_ids}

    async def _load[R: EntityRow, T](
        self, model: type[R], ids: frozenset[str], convert: Callable[[R], T]
    ) -> dict[str, T | None]:
        if not ids:
            return {}
        rows = await self._session.scalars(_scoped(model, self._scope).where(model.id.in_(ids)))
        found = {row.id: convert(row) for row in rows}
        return {i: found.get(i) for i in ids}

    async def save(
        self, result: CommitResult, *, actor: Actor, traceparent: str | None = None
    ) -> list[Envelope]:
        head = self._workspace.head_seq
        now = self._clock()
        envelopes: list[Envelope] = []
        for offset, event in enumerate(result.events, start=1):
            thread_id, run_id = scope_of(event)
            envelopes.append(
                Envelope(
                    seq=head + offset,
                    id=str(uuid.uuid4()),
                    ts=now,
                    workspace_id=self._scope.workspace_id,
                    thread_id=thread_id,
                    run_id=run_id,
                    actor=actor,
                    traceparent=traceparent,
                    event=event,
                )
            )
        self._workspace.head_seq = head + len(envelopes)
        for artifact in result.artifacts:
            artifact_row = await self._entity(ArtifactRow, artifact.id)
            artifact_row.kind = artifact.kind
            artifact_row.version = artifact.version
            artifact_row.archived = artifact.archived
            artifact_row.data = artifact.data.to_json()
            artifact_row.updated_by = artifact.updated_by.model_dump(mode="json")
        for proposal in result.proposals:
            proposal_row = await self._entity(ProposalRow, proposal.id)
            proposal_row.status = proposal.status
            proposal_row.body = proposal.model_dump(mode="json")
        for thread in result.threads:
            thread_row = await self._entity(ThreadRow, thread.id)
            thread_row.body = thread.model_dump(mode="json")
        for run in result.runs:
            run_row = await self._entity(RunRow, run.id)
            run_row.thread_id = run.thread_id
            run_row.status = run.status
            run_row.body = run.model_dump(mode="json")
        self._session.add_all(
            MessageRow(**self._key, id=message_id) for message_id in result.messages
        )
        self._session.add_all(
            RevisionRow(
                **self._key,
                artifact_id=revision.artifact_id,
                version=revision.version,
                body=revision.model_dump(mode="json"),
            )
            for revision in result.revisions
        )
        self._session.add_all(
            EventRow(
                **self._key,
                seq=envelope.seq,
                event_type=envelope.event.type,
                thread_id=envelope.thread_id,
                envelope=envelope.model_dump(mode="json"),
            )
            for envelope in envelopes
        )
        return envelopes

    async def append_history(self, thread_id: ThreadId, messages: bytes) -> None:
        self._history.append((thread_id, messages))

    def finish(self) -> int:
        """Add the history appended in this transaction at the log's final head; return it."""
        head = self._workspace.head_seq
        self._session.add_all(
            HistoryRow(
                **self._key,
                position=self._next_position(),
                thread_id=thread_id,
                seq=head,
                messages=messages,
            )
            for thread_id, messages in self._history
        )
        return head

    @property
    def _key(self) -> dict[str, str]:
        return {"tenant_id": self._scope.tenant_id, "workspace_id": self._scope.workspace_id}

    async def _entity[R: EntityRow](self, model: type[R], entity_id: str) -> R:
        """Return the entity's row, adding it in creation order if it is new."""
        key = (self._scope.tenant_id, self._scope.workspace_id, entity_id)
        row = await self._session.get(model, key)
        if row is None:
            row = model(**self._key, id=entity_id, position=self._next_position())
            self._session.add(row)
        return row

    def _next_position(self) -> int:
        self._workspace.last_position += 1
        return self._workspace.last_position


async def _lock_workspace(session: AsyncSession, scope: Scope) -> WorkspaceRow:
    """Lock the workspace's row, creating it first if the workspace is new."""
    new = WorkspaceRow(
        tenant_id=scope.tenant_id, workspace_id=scope.workspace_id, head_seq=0, last_position=0
    )
    return await _locked(session, WorkspaceRow, (scope.tenant_id, scope.workspace_id), new)


async def _locked[R: ScopedRow](
    session: AsyncSession, model: type[R], key: tuple[str, ...], new: R
) -> R:
    """Lock a row (``SELECT ... FOR UPDATE``), inserting ``new`` first if it does not exist."""
    while (row := await session.get(model, key, with_for_update=True)) is None:
        # A concurrent transaction may insert the row first. Then this insert fails, and the
        # next lookup waits for that transaction to end and locks its row instead.
        with contextlib.suppress(IntegrityError):
            async with session.begin_nested():
                session.add(new)
    return row


def _scoped[R: ScopedRow](model: type[R], scope: Scope) -> Select[R]:
    return select(model).where(
        model.tenant_id == scope.tenant_id, model.workspace_id == scope.workspace_id
    )


def _entities[R: EntityRow](model: type[R], scope: Scope) -> Select[R]:
    return _scoped(model, scope).order_by(model.position)


def _versioned(row: ArtifactRow) -> Versioned[Artifact]:
    return load_versioned(
        id=row.id,
        kind=row.kind,
        version=row.version,
        data=row.data,
        updated_by=row.updated_by,
        archived=row.archived,
    )


def _proposal(row: ProposalRow) -> Proposal:
    return Proposal.model_validate(row.body)


def _thread(row: ThreadRow) -> Thread:
    return Thread.model_validate(row.body)


def _run(row: RunRow) -> Run:
    return Run.model_validate(row.body)


class SqlStorage:
    """Storage in a SQL database, through SQLAlchemy's asyncio extension.

    Create the tables with :func:`~artifactr.sql.migrate` first. The same code runs on
    PostgreSQL (with its default ``READ COMMITTED`` isolation) and on SQLite, whose engines
    must come from :func:`~artifactr.sql.create_sqlite_engine`.

    Args:
        engine: The database to use. The storage does not dispose of it.
        clock: Returns the current time, for envelope timestamps and lease expiry. Defaults
            to the system clock in UTC.
        poll_interval: How often a subscription checks the log for envelopes committed by
            other processes. Commits made through this storage wake its subscriptions at once.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        clock: Clock = _utc_now,
        poll_interval: timedelta = timedelta(seconds=0.5),
    ) -> None:
        self._engine = engine
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._clock = clock
        self._poll_interval = poll_interval.total_seconds()
        self._heads: dict[Scope, int] = {}
        self._committed = asyncio.Condition()

    @asynccontextmanager
    async def transaction(self, scope: Scope) -> AsyncGenerator[_Transaction]:
        """Begin a transaction; it holds the workspace row's lock until it ends."""
        async with self._sessions() as session, session.begin():
            transaction = _Transaction(
                session, scope, await _lock_workspace(session, scope), self._clock
            )
            yield transaction
            head = transaction.finish()
        async with self._committed:
            self._heads[scope] = max(head, self._heads.get(scope, 0))
            self._committed.notify_all()

    async def artifact(self, scope: Scope, artifact_id: ArtifactId) -> Versioned[Artifact] | None:
        """Return an artifact's current version, or None."""
        return await self._one(ArtifactRow, scope, artifact_id, _versioned)

    async def artifacts(
        self, scope: Scope, *, kind: str | None = None, include_archived: bool = False
    ) -> list[Versioned[Artifact]]:
        """Return current artifacts, optionally of one kind, oldest first."""
        query = _entities(ArtifactRow, scope)
        if kind is not None:
            query = query.where(ArtifactRow.kind == kind)
        if not include_archived:
            query = query.where(ArtifactRow.archived.is_(False))
        return [_versioned(row) for row in await self._all(query)]

    async def revisions(self, scope: Scope, artifact_id: ArtifactId) -> list[Revision]:
        """Return an artifact's revisions, oldest first."""
        query = (
            _scoped(RevisionRow, scope)
            .where(RevisionRow.artifact_id == artifact_id)
            .order_by(RevisionRow.version)
        )
        return [Revision.model_validate(row.body) for row in await self._all(query)]

    async def thread(self, scope: Scope, thread_id: ThreadId) -> Thread | None:
        """Return a thread, or None."""
        return await self._one(ThreadRow, scope, thread_id, _thread)

    async def threads(self, scope: Scope) -> list[Thread]:
        """Return every thread, oldest first."""
        return [_thread(row) for row in await self._all(_entities(ThreadRow, scope))]

    async def proposal(self, scope: Scope, proposal_id: ProposalId) -> Proposal | None:
        """Return a proposal, or None."""
        return await self._one(ProposalRow, scope, proposal_id, _proposal)

    async def proposals(
        self,
        scope: Scope,
        *,
        status: Literal["pending", "accepted", "rejected"] | None = None,
    ) -> list[Proposal]:
        """Return proposals, optionally with one status, oldest first."""
        query = _entities(ProposalRow, scope)
        if status is not None:
            query = query.where(ProposalRow.status == status)
        return [_proposal(row) for row in await self._all(query)]

    async def run(self, scope: Scope, run_id: RunId) -> Run | None:
        """Return a run, or None."""
        return await self._one(RunRow, scope, run_id, _run)

    async def runs(
        self,
        scope: Scope,
        *,
        thread_id: ThreadId | None = None,
        status: RunStatus | None = None,
    ) -> list[Run]:
        """Return runs, optionally of one thread and with one status, oldest first."""
        query = _entities(RunRow, scope)
        if thread_id is not None:
            query = query.where(RunRow.thread_id == thread_id)
        if status is not None:
            query = query.where(RunRow.status == status)
        return [_run(row) for row in await self._all(query)]

    async def head_seq(self, scope: Scope) -> int:
        """Return the log's latest ``seq``, or 0 if it is empty."""
        async with self._sessions() as session:
            head = await session.scalar(
                select(WorkspaceRow.head_seq).where(
                    WorkspaceRow.tenant_id == scope.tenant_id,
                    WorkspaceRow.workspace_id == scope.workspace_id,
                )
            )
        return head or 0

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
        The filter and both ends of the window are in the query, and the last are read
        backwards from the end of the log.
        """
        query = _scoped(EventRow, scope).where(EventRow.seq > after_seq)
        if before_seq is not None:
            query = query.where(EventRow.seq < before_seq)
        if threads is not None:
            query = query.where(_delivered_to(threads))
        if last is not None:
            query = query.order_by(EventRow.seq.desc()).limit(last)
        else:
            query = query.order_by(EventRow.seq).limit(limit)
        envelopes = [Envelope.model_validate(row.envelope) for row in await self._all(query)]
        return envelopes if last is None else envelopes[::-1]

    async def subscribe(self, scope: Scope, *, after_seq: int = 0) -> AsyncGenerator[Envelope]:
        """Yield stored envelopes after ``after_seq``, then each new one as it commits.

        New envelopes arrive at once when they were committed through this storage, and
        within ``poll_interval`` otherwise.
        """
        cursor = after_seq
        while True:
            # Read a page and close the session before yielding, so a subscriber that stops
            # iterating holds no connection.
            page = await self.read(scope, after_seq=cursor, limit=_PAGE)
            for envelope in page:
                yield envelope
            if page:
                cursor = page[-1].seq
            else:
                await self._wait_for_commit(scope, cursor)

    async def _wait_for_commit(self, scope: Scope, cursor: int) -> None:
        async with self._committed:
            committed = self._committed.wait_for(lambda: self._heads.get(scope, 0) > cursor)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(committed, self._poll_interval)

    async def history(self, scope: Scope, thread_id: ThreadId) -> Sequence[HistoryChunk]:
        """Return a thread's history chunks, in the order they were appended."""
        query = (
            _scoped(HistoryRow, scope)
            .where(HistoryRow.thread_id == thread_id)
            .order_by(HistoryRow.position)
        )
        return [HistoryChunk(seq=row.seq, messages=row.messages) for row in await self._all(query)]

    async def acquire_lease(self, scope: Scope, key: str, holder: str, ttl: timedelta) -> bool:
        """Take or renew an exclusive lease. Return False if another holder has it."""
        # Normalized to UTC, because SQLite compares timestamps as text.
        now = self._clock().astimezone(UTC)
        lease = _lease(scope, key)
        try:
            async with self._engine.begin() as connection:
                taken = await connection.execute(
                    update(LeaseRow)
                    .where(*lease, or_(LeaseRow.holder == holder, LeaseRow.expires_at <= now))
                    .values(holder=holder, expires_at=now + ttl)
                )
                if taken.rowcount == 0:
                    await connection.execute(
                        insert(LeaseRow).values(
                            tenant_id=scope.tenant_id,
                            workspace_id=scope.workspace_id,
                            key=key,
                            holder=holder,
                            expires_at=now + ttl,
                        )
                    )
        except IntegrityError:
            # Another holder has an unexpired lease, or took it first.
            return False
        return True

    async def release_lease(self, scope: Scope, key: str, holder: str) -> None:
        """Release a lease if ``holder`` has it."""
        async with self._engine.begin() as connection:
            await connection.execute(
                delete(LeaseRow).where(*_lease(scope, key), LeaseRow.holder == holder)
            )

    async def cursor(self, scope: Scope, name: str) -> int:
        """Return how far a named consumer of the log has got: the ``seq`` saved, or 0."""
        async with self._sessions() as session:
            cursor = await session.get(CursorRow, (scope.tenant_id, scope.workspace_id, name))
        return 0 if cursor is None else cursor.seq

    async def save_cursor(self, scope: Scope, name: str, seq: int) -> None:
        """Save how far a named consumer of the log has got; a cursor only moves forward.

        The cursor's row is locked while it is compared, so saves from several processes
        leave the furthest.
        """
        key = (scope.tenant_id, scope.workspace_id, name)
        new = CursorRow(
            tenant_id=scope.tenant_id, workspace_id=scope.workspace_id, name=name, seq=seq
        )
        async with self._sessions() as session, session.begin():
            cursor = await _locked(session, CursorRow, key, new)
            cursor.seq = max(cursor.seq, seq)

    async def _one[R: EntityRow, T](
        self, model: type[R], scope: Scope, entity_id: str, convert: Callable[[R], T]
    ) -> T | None:
        async with self._sessions() as session:
            row = await session.get(model, (scope.tenant_id, scope.workspace_id, entity_id))
        return None if row is None else convert(row)

    async def _all[R: ScopedRow](self, query: Select[R]) -> Sequence[R]:
        async with self._sessions() as session:
            return (await session.scalars(query)).all()


def _delivered_to(threads: Collection[ThreadId]) -> ColumnElement[bool]:
    """Whether a subscriber following ``threads`` receives an event, as ``delivered_to`` says."""
    return or_(
        EventRow.thread_id.is_(None),
        EventRow.event_type.in_(sorted(WORKSPACE_SCOPED)),
        EventRow.thread_id.in_(sorted(threads)),
    )


def _lease(scope: Scope, key: str) -> tuple[ColumnElement[bool], ...]:
    return (
        LeaseRow.tenant_id == scope.tenant_id,
        LeaseRow.workspace_id == scope.workspace_id,
        LeaseRow.key == key,
    )
