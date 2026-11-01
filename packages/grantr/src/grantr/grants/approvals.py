"""grantr's store of approvals: lattice-core's ``Approvals``, kept per tenant and audited.

An approval is asked, answered, taken, withdrawn and expired in a transaction of its tenant,
with its audit entry, so the first answer wins: the transaction reads it pending and settles it
while every other change to the tenant waits (lattice RFC-0011, grantr ADR-0038). grantr decides
who may answer, from what it already keeps: the subjects and groups an approval names, by
grantr's own groups, and the holders of its action on the approval's workspace, by grantr's
own grants. A person delegates by granting the action.

An approval's id names its tenant, ``apr~<tenant>~<token>``, since a tenant's id has no ``~``:
each read and change is the tenant's alone, as row-level security keeps it.
"""

import asyncio
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from typing import Final, Literal

from grantr.core import (
    ApprovalAnswered,
    ApprovalAsked,
    ApprovalClosed,
    AuditEntry,
    AuditEvent,
    Invalid,
    Member,
    ServicePrincipal,
    Subject,
    TenantId,
    User,
    WorkspaceId,
)
from grantr.core.ids import TENANT_ID
from grantr.grants.storage import Reads, Storage, Transaction
from lattice_core.approvals import (
    CONFIRM_SURFACE,
    AlreadyAnswered,
    Answer,
    Answered,
    Approval,
    ApprovalId,
    ApprovalRequest,
    DigestMismatch,
    NotAnAnswerer,
    NotApproved,
    NotPending,
    ScopeNotOffered,
    State,
    UnknownApproval,
)
from lattice_core.approvals import Subject as Answerer
from lattice_core.capabilities import Caller, PersonCaller, Scope

type Record = Callable[[TenantId | None, Subject | None, AuditEvent], Awaitable[AuditEntry]]
"""Appends an audit entry in a change's transaction."""

type Change = Callable[[TenantId], AbstractAsyncContextManager[tuple[Transaction, Record]]]
"""A change to one tenant: its transaction, and how to record its audit entries."""

type Holds = Callable[[Reads, TenantId, Member, str, WorkspaceId], Awaitable[bool]]
"""Whether a member holds an action on a workspace, as an answerer: a service principal by a
grant made to it, and not to a group it is in."""

type IsMember = Callable[[Reads, TenantId, Member], Awaitable[bool]]
"""Whether a user or service principal is a member of a tenant."""

PREFIX: Final = "apr"
"""What an approval's id starts with."""

EXPIRED: Final = "past its deadline unanswered"
"""Why the sweep expires an approval."""

POLL: Final = timedelta(seconds=1)
"""How often :meth:`GrantrApprovals.watch` reads an approval it waits on, by default."""


def _person(caller: Caller) -> str | None:
    """The id of the person a caller is or acts for, if any."""
    return caller.id if isinstance(caller, PersonCaller) else caller.on_behalf_of


def _member(answerer: Answerer) -> Member:
    """The grantr subject an answerer is: a service principal, or a user."""
    return ServicePrincipal(id=answerer.id) if answerer.service else User(id=answerer.id)


def _tenant_of(id: ApprovalId) -> TenantId:
    """The tenant an approval's id names.

    Raises:
        UnknownApproval: If the id isn't an approval's id.
    """
    prefix, _, rest = id.partition("~")
    tenant, _, token = rest.partition("~")
    if prefix != PREFIX or not token or "~" in token or not TENANT_ID.fullmatch(tenant):
        raise UnknownApproval(id)
    return tenant


async def _stored(reads: Reads, id: ApprovalId) -> Approval:
    """The approval of the id, as it stands.

    Raises:
        UnknownApproval: If there is no approval of the id.
    """
    approval = await reads.approval(_tenant_of(id), id)
    if approval is None:
        raise UnknownApproval(id)
    return approval


def _utc_now() -> datetime:
    return datetime.now(UTC)


class GrantrApprovals:
    """lattice-core's ``Approvals``, in grantr's store: what :meth:`Grants.approvals` returns.

    Every change is in its tenant's transaction, with its audit entry: an approval asked
    (``approval_asked``), answered (``approval_answered``), or closed unanswered, expired or
    withdrawn (``approval_closed``). The call an approval lets through is the enforcer's to
    audit, so taking it records nothing here.

    A subject may answer if it is a member of the approval's tenant and:

    - the approval names it, or a group it is in, by grantr's groups; or it holds the
      approval's action on the approval's workspace, by grantr's grants;
    - never, if a different approver is asked, when it is the person who asked;
    - a confirmation only when it is the one person named, on
      :data:`~lattice_core.approvals.CONFIRM_SURFACE`;
    - a service principal only by holding the action through a grant made to it: the
      subjects and groups an approval names are people, since a principal's id may be a
      person's too, and it never answers a confirmation.

    An approval is shown (:meth:`shown`) to whoever may answer it, and to the person it was
    asked for, while each is a member of its tenant; to anyone else it isn't there.

    The groups an answerer says it is in count for nothing: grantr's own do. Nothing offers a
    scope yet, so an answer that carries one is refused. An approval past its deadline takes
    no answer, though only :meth:`expire_due`, the sweep, closes it.

    Args:
        storage: grantr's storage, for the reads outside a change.
        change: A change to one tenant, from :class:`~grantr.grants.Grants`.
        holds: Whether a member holds an action on a workspace, from
            :class:`~grantr.grants.Grants`.
        is_member: Whether a subject is a member of a tenant, from
            :class:`~grantr.grants.Grants`.
        clock: The time now; the system's, in UTC, if omitted.
        poll: How often :meth:`watch` reads an approval it waits on.
    """

    def __init__(
        self,
        storage: Storage,
        *,
        change: Change,
        holds: Holds,
        is_member: IsMember,
        clock: Callable[[], datetime] | None = None,
        poll: timedelta = POLL,
    ) -> None:
        self._storage = storage
        self._change = change
        self._holds = holds
        self._is_member = is_member
        self._clock = clock or _utc_now
        self._poll = poll.total_seconds()

    async def may_answer(self, approval: Approval, answerer: Answerer, /) -> bool:
        """Whether the answerer may answer the approval, on some surface."""
        return await self._may_answer(self._storage, approval, answerer)

    async def _may_answer(self, reads: Reads, approval: Approval, answerer: Answerer) -> bool:
        answerers = approval.answerers
        tenant = approval.scope.tenant_id
        member = _member(answerer)
        if answerers.different_approver and answerer.id == _person(approval.asked_by):
            return False
        if not await self._is_member(reads, tenant, member):
            return False
        if answerers.confirmation:
            return not answerer.service and answerer.id in answerers.subjects
        # Subjects and groups name people: a principal's id may be a person's too.
        if not answerer.service:
            if answerer.id in answerers.subjects:
                return True
            groups = await reads.groups(tenant) if answerers.groups else {}
            if any(member in groups.get(group, frozenset()) for group in answerers.groups):
                return True
        return answerers.action is not None and await self._holds(
            reads, tenant, member, answerers.action, approval.scope.workspace_id
        )

    async def ask(self, request: ApprovalRequest, /) -> Approval:
        """Ask an approval, pending, and return it.

        Raises:
            Invalid: If there is no tenant of the request's scope.
        """
        tenant = request.scope.tenant_id
        if not TENANT_ID.fullmatch(tenant):
            raise Invalid("a tenant's id isn't empty, and has no ~")
        async with self._change(tenant) as (tx, record):
            if not await tx.tenant(tenant):
                raise Invalid(f"there is no tenant {tenant}")
            approval = Approval(
                **dict(request),
                id=f"{PREFIX}~{tenant}~{secrets.token_hex(16)}",
                asked_at=self._clock(),
                state="pending",
            )
            person = _person(request.asked_by)
            caller = request.asked_by
            event = ApprovalAsked(
                approval=approval.id,
                workspace=request.scope.workspace_id,
                capability=request.capability,
                caller=f"{caller.kind}:{caller.id}",
            )
            await record(tenant, None if person is None else User(id=person), event)
            await tx.put_approval(approval)
            return approval

    async def get(self, id: ApprovalId, /) -> Approval:
        """Return the approval as it stands.

        Raises:
            UnknownApproval: If there is no approval of the id.
        """
        return await _stored(self._storage, id)

    async def answer(self, id: ApprovalId, answer: Answer, /, *, subject: Answerer) -> Approval:
        """Answer a pending approval as the subject, and return it settled.

        Raises:
            UnknownApproval: If there is no approval of the id.
            AlreadyAnswered: If someone answered first.
            NotPending: If it expired, is past its deadline, or was withdrawn.
            NotAnAnswerer: If the subject may not answer it, or not on that surface.
            DigestMismatch: If the answer was given to other arguments.
            ScopeNotOffered: If the answer carries a scope: nothing offers one yet.
        """
        async with self._change(_tenant_of(id)) as (tx, record):
            approval = await _stored(tx, id)
            if approval.answer is not None:
                raise AlreadyAnswered(approval, approval.answer)
            if approval.state != "pending":
                raise NotPending(approval)
            now = self._clock()
            if approval.deadline <= now:
                raise NotPending(approval, f"approval {id} is past its deadline")
            if not await self._may_answer(tx, approval, subject):
                raise NotAnAnswerer(f"{subject.id} may not answer approval {id}")
            if approval.answerers.confirmation and answer.surface != CONFIRM_SURFACE:
                raise NotAnAnswerer(f"approval {id} is confirmed on {CONFIRM_SURFACE} alone")
            if answer.arguments_digest != approval.arguments_digest:
                raise DigestMismatch(f"approval {id} asks about other arguments")
            if answer.scope is not None:
                raise ScopeNotOffered(f"approval {id} takes no scoped answer")
            event = ApprovalAnswered(approval=id, approved=answer.approved, surface=answer.surface)
            await record(approval.scope.tenant_id, _member(subject), event)
            state: State = "approved" if answer.approved else "denied"
            answered = Answered(**dict(answer), by=subject, at=now)
            settled = approval.model_copy(update={"state": state, "answer": answered})
            await tx.put_approval(settled)
            return settled

    async def take(self, id: ApprovalId, /) -> Approval:
        """Take an approved approval for the one call it lets through, and return it, taken.

        Raises:
            UnknownApproval: If there is no approval of the id.
            NotApproved: If it isn't approved, or was taken already.
        """
        async with self._change(_tenant_of(id)) as (tx, _):
            approval = await _stored(tx, id)
            if approval.state != "approved" or approval.taken_at is not None:
                raise NotApproved(approval)
            taken = approval.model_copy(update={"taken_at": self._clock()})
            await tx.put_approval(taken)
            return taken

    async def withdraw(self, id: ApprovalId, reason: str, /) -> Approval:
        """Withdraw a pending approval, because its run stopped or its arguments changed.

        Raises:
            UnknownApproval: If there is no approval of the id.
            NotPending: If it is settled already.
        """
        async with self._change(_tenant_of(id)) as (tx, record):
            approval = await _stored(tx, id)
            return await self._close(tx, record, approval, "withdrawn", reason)

    async def _close(
        self,
        tx: Transaction,
        record: Record,
        approval: Approval,
        state: Literal["expired", "withdrawn"],
        reason: str,
    ) -> Approval:
        if approval.state != "pending":
            raise NotPending(approval)
        event = ApprovalClosed(approval=approval.id, state=state, reason=reason)
        await record(approval.scope.tenant_id, None, event)
        closed = approval.model_copy(update={"state": state, "reason": reason})
        await tx.put_approval(closed)
        return closed

    async def expire_due(self) -> list[Approval]:
        """Expire every pending approval past its deadline, in every tenant: the sweep.

        Each tenant's are expired in one transaction of its own.

        Returns:
            The approvals it expired, tenant by tenant, oldest first.
        """
        expired: list[Approval] = []
        for tenant in await self._storage.tenants():
            async with self._change(tenant) as (tx, record):
                expired += [
                    await self._close(tx, record, approval, "expired", EXPIRED)
                    for approval in await tx.approvals(tenant, due=self._clock())
                ]
        return expired

    async def pending(self, scope: Scope, subject: Answerer, /) -> list[Approval]:
        """Return the approvals pending in the scope that the subject may answer, oldest first."""
        return await self._answerable(scope.tenant_id, subject, scope.workspace_id)

    async def answerable(self, tenant: TenantId, subject: Answerer, /) -> list[Approval]:
        """Return the approvals pending in the tenant that the subject may answer, oldest first.

        Those of every workspace: the list a person answers from.
        """
        return await self._answerable(tenant, subject, None)

    async def _answerable(
        self, tenant: TenantId, subject: Answerer, workspace: WorkspaceId | None
    ) -> list[Approval]:
        if not TENANT_ID.fullmatch(tenant):
            return []
        asked = await self._storage.approvals(tenant, workspace=workspace)
        return [
            approval
            for approval in asked
            if await self._may_answer(self._storage, approval, subject)
        ]

    async def shown(self, id: ApprovalId, subject: Answerer, /) -> Approval:
        """Return the approval as it stands, to one who may answer it or who it was asked for.

        Either is a member of its tenant still; the approval is shown whatever its state.

        Raises:
            UnknownApproval: If there is no approval of the id, or the subject may see it
                neither way: whether it exists isn't said.
        """
        approval = await _stored(self._storage, id)
        tenant = approval.scope.tenant_id
        asker = not subject.service and subject.id == _person(approval.asked_by)
        if asker and await self._is_member(self._storage, tenant, User(id=subject.id)):
            return approval
        if await self._may_answer(self._storage, approval, subject):
            return approval
        raise UnknownApproval(id)

    async def watch(self, id: ApprovalId, /) -> AsyncIterator[Approval]:
        """Yield the approval as it stands, then each change, until it is settled.

        It reads the approval every ``poll`` while it is pending.

        Raises:
            UnknownApproval: If there is no approval of the id.
        """
        approval = await self.get(id)
        yield approval
        while approval.state == "pending":
            await asyncio.sleep(self._poll)
            now = await self.get(id)
            if now != approval:
                approval = now
                yield approval
