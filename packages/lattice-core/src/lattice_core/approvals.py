"""Approvals: one object for every ask a person answers before a call goes ahead.

An :class:`Approval` is asked once, for one call of one capability, with a :class:`Rendering`
of exactly what would happen and the digest of the call's arguments, which an :class:`Answer`
must carry to count. Its :class:`Answerers` say who may answer: a grantr action, named subjects
or groups, and whether the answer must come from someone other than the caller. The first
answer wins; the others are refused with it. An approval is otherwise withdrawn, when its run
stops or its arguments change, or expires at its deadline (lattice RFC-0011).

Two shapes stand for more than one call. An answer may carry an :class:`AnswerScope`, which
only the patterns the request offered may fill (for the code sessions' "always allow"), and a
plan's approval ``covers`` the :class:`ListedAction` entries a run's plan lists, which the
enforcer asks a :class:`Coverage` about before it asks anew.

This module declares the contract: the types, the ports a store (:class:`Approvals`), a policy
(:class:`ApprovalPolicy`), a plan's coverage (:class:`Coverage`) and a surface
(:class:`ApprovalSurface`) implement, and their refusals. grantr stores approvals;
:class:`FakeApprovals` is an in-memory store for tests, with the same semantics, and
:class:`NoCoverage` the coverage of an application without plans.

The contract's version is :data:`CONTRACT`, and its JSON Schema, which :func:`contract_schema`
returns, is checked in at ``schemas/approvals.v1.json``: regenerate it with ``moon run
lattice-core:schema`` (:mod:`lattice_core.contracts`).
"""

import asyncio
import hashlib
import json
import re
from collections.abc import AsyncIterator, Callable, Iterable
from datetime import UTC, datetime
from functools import partial
from itertools import count
from typing import Final, Literal, Protocol, Self, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator

from lattice_core.capabilities import (
    ACTION,
    NAME,
    VERSION,
    CallContext,
    Caller,
    Capability,
    JsonObject,
    PersonCaller,
    Scope,
    Tier,
    Via,
)

__all__ = [
    "CONFIRM_SURFACE",
    "CONTRACT",
    "DIGEST",
    "STATES",
    "AlreadyAnswered",
    "Answer",
    "AnswerScope",
    "Answered",
    "Answerers",
    "Approval",
    "ApprovalError",
    "ApprovalId",
    "ApprovalPolicy",
    "ApprovalRequest",
    "ApprovalSurface",
    "Approvals",
    "Coverage",
    "DigestMismatch",
    "FakeApprovals",
    "ListedAction",
    "NoCoverage",
    "NotAnAnswerer",
    "NotApproved",
    "NotPending",
    "Rendering",
    "ScopeNotOffered",
    "State",
    "Subject",
    "UnknownApproval",
    "arguments_digest",
    "contract_schema",
]

CONTRACT: Final = "1.0.0"
"""The contract's version. A removed field or a changed meaning is a major version; an optional
field is a minor one, and a consumer treats a value it doesn't know as the strictest."""

type ApprovalId = str
"""An approval's id, opaque, given by the store that asked it."""

State = Literal["pending", "approved", "denied", "expired", "withdrawn"]
"""Where an approval stands: waiting for an answer, answered yes or no, past its deadline
unanswered, or withdrawn before an answer."""

STATES: Final[tuple[State, ...]] = ("pending", "approved", "denied", "expired", "withdrawn")
"""The states an approval may be in."""

DIGEST: Final = re.compile(r"[0-9a-f]{64}")
"""A digest's form: SHA-256, in lowercase hexadecimal."""

CONFIRM_SURFACE: Final = "portalr:confirm"
"""The one surface a caller's own confirmation is answered on: portalr's signed-in confirm
page, fresh, for this action and its target."""


def _canonical(value: JsonValue) -> bytes:
    """Return a JSON value's canonical form: keys sorted, no spaces, UTF-8."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def arguments_digest(arguments: JsonObject) -> str:
    """Return the digest of a call's arguments, which an answer must carry to count.

    It is the SHA-256 of their canonical JSON, keys sorted and no spaces, so two equal sets of
    arguments have one digest however their keys were ordered.
    """
    return hashlib.sha256(_canonical(arguments)).hexdigest()


def _digest(value: str, what: str) -> str:
    if not DIGEST.fullmatch(value):
        raise ValueError(f"{what} is a SHA-256 in lowercase hexadecimal, not {value!r}")
    return value


class Rendering(BaseModel):
    """Exactly what a call would do, as a person is shown it before they answer.

    Raises:
        ValueError: If the title is empty, or neither a diff nor the arguments are given.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    title: str
    """What is asked, in a line: "Send the weekly report to finance@"."""
    summary: str = ""
    """More of what it does, where a line isn't enough."""
    diff: str | None = None
    """The change it would make, as a unified diff, where it changes text."""
    arguments: JsonObject | None = None
    """The call's arguments, where no diff shows what it does."""

    @model_validator(mode="after")
    def _shows_something(self) -> Self:
        if not self.title.strip():
            raise ValueError("a rendering needs a title")
        if self.diff is None and self.arguments is None:
            raise ValueError("a rendering shows a diff or the arguments")
        return self


class Answerers(BaseModel):
    """Who may answer an approval.

    Anyone who holds ``action`` may answer, or is named in ``subjects``, or is in one of
    ``groups``. A person delegates by a grantr grant of the action, with an expiry, not by a
    field here. A service principal answers only where it is named or holds the action itself,
    and never a ``confirmation``.

    Raises:
        ValueError: If it names no one, ``action`` isn't a grantr action, or a confirmation
            isn't one subject's alone.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    action: str | None = None
    """The grantr action whose holders may answer, such as ``grantr:answer_approval``."""
    subjects: frozenset[str] = frozenset()
    """The ids of the subjects who may answer."""
    groups: frozenset[str] = frozenset()
    """The ids of the groups whose members may answer."""
    different_approver: bool = False
    """Whether the answer must come from someone other than the person who asked."""
    confirmation: bool = False
    """Whether it is the caller's own confirmation of an ``admin_high`` call: answered only by
    the one subject named, on :data:`CONFIRM_SURFACE`, never by the client that called, by
    elicitation or by a push action."""

    @model_validator(mode="after")
    def _names_someone(self) -> Self:
        if self.action is None and not self.subjects and not self.groups:
            raise ValueError("answerers name an action, subjects or groups")
        if self.action is not None and not ACTION.fullmatch(self.action):
            raise ValueError(f"a grantr action is package:action, not {self.action!r}")
        if self.confirmation and (
            len(self.subjects) != 1
            or self.action is not None
            or self.groups
            or self.different_approver
        ):
            raise ValueError("a confirmation is answered by the one subject it names, alone")
        return self


class AnswerScope(BaseModel):
    """How far an answer stands beyond its own call: for a run or a session, for what patterns.

    Raises:
        ValueError: If it names no pattern.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    within: Literal["session", "run"]
    """How long it stands: the code session's life or the run's."""
    patterns: tuple[str, ...] = Field(min_length=1)
    """What it allows, from those the request offered, such as a command's prefix."""
    expires_at: AwareDatetime | None = None
    """When it stops standing, if before the session or run ends."""


class ListedAction(BaseModel):
    """An action a run's plan lists, which the plan's approval pre-approves.

    ``digest`` covers the step, the capability's whole definition, the target and the calls
    allowed, so a capability that changes (another major, tier or effects) is no longer covered.
    Build one with :meth:`of`, which computes it.

    Raises:
        ValueError: If the capability's name isn't of :data:`~lattice_core.capabilities.NAME`'s
            form, or the digest isn't a SHA-256.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    step: str
    """The id of the plan's step that calls it."""
    capability: str
    """The capability's name."""
    major: int = Field(ge=0)
    """The capability's major version."""
    tier: Tier
    """The capability's tier."""
    target: JsonValue = None
    """The condition the call's arguments must meet, as its JSON (lattice RFC-0012), or None
    for any arguments."""
    max_calls: int | None = Field(default=None, ge=1)
    """How many calls a run may make under it, or None for no limit beyond the run's."""
    digest: str
    """The SHA-256 of the step, the capability's definition, the target and ``max_calls``."""

    @model_validator(mode="after")
    def _well_formed(self) -> Self:
        if not NAME.fullmatch(self.capability):
            raise ValueError(f"a capability's name is provider.tool, not {self.capability!r}")
        _digest(self.digest, "a listed action's digest")
        return self

    @classmethod
    def of(
        cls,
        step: str,
        capability: Capability,
        *,
        target: JsonValue = None,
        max_calls: int | None = None,
    ) -> Self:
        """Return the listed action of a step that calls the capability, with its digest."""
        definition = capability.model_dump(mode="json")
        listed: JsonValue = {
            "step": step,
            "capability": definition,
            "target": target,
            "max_calls": max_calls,
        }
        return cls(
            step=step,
            capability=capability.name,
            major=int(capability.version.split(".", 1)[0]),
            tier=capability.tier,
            target=target,
            max_calls=max_calls,
            digest=hashlib.sha256(_canonical(listed)).hexdigest(),
        )


class ApprovalRequest(BaseModel):
    """What a call asks a person to approve: which call, shown how, of whom, by when.

    Raises:
        ValueError: If the capability's name or version is malformed, the digest isn't a
            SHA-256, or a confirmation is asked of anyone but the person who called.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    scope: Scope
    """The tenant's workspace the call is made in."""
    capability: str
    """The name of the capability called."""
    version: str
    """The version of the capability called."""
    rendering: Rendering
    """Exactly what the call would do."""
    arguments_digest: str
    """The digest of the call's arguments (:func:`arguments_digest`), which an answer binds to."""
    asked_by: Caller
    """Who called: a person, or an agent's run or a code session and the person it acts for."""
    via: Via | None = None
    """The outside client the call came through, or None for lattice's own surfaces. A
    different approver is never offered it there."""
    answerers: Answerers
    """Who may answer."""
    deadline: AwareDatetime
    """When it expires unanswered."""
    covers: tuple[ListedAction, ...] = ()
    """The listed actions a plan's approval pre-approves; empty for any other."""
    scopes_offered: tuple[str, ...] = ()
    """The patterns an answer's scope may name; empty, so no answer may carry a scope, unless
    the capability offers some."""

    @model_validator(mode="after")
    def _well_formed(self) -> Self:
        if not NAME.fullmatch(self.capability):
            raise ValueError(f"a capability's name is provider.tool, not {self.capability!r}")
        if not VERSION.fullmatch(self.version):
            raise ValueError(f"a capability's version is MAJOR.MINOR.PATCH, not {self.version!r}")
        _digest(self.arguments_digest, "an approval's arguments digest")
        person = _person(self.asked_by)
        if self.answerers.confirmation and (
            person is None or self.answerers.subjects != frozenset({person})
        ):
            raise ValueError("a confirmation is asked of the person who called, alone")
        return self


def _person(caller: Caller) -> str | None:
    """Return the id of the person a caller is or acts for, if any."""
    return caller.id if isinstance(caller, PersonCaller) else caller.on_behalf_of


class Subject(BaseModel):
    """Someone who answers: a person, or a service principal, by their grantr id."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    id: str
    """The subject's id."""
    service: bool = False
    """Whether it is a service principal rather than a person."""
    groups: frozenset[str] = frozenset()
    """The ids of the groups it is a member of."""


class Answer(BaseModel):
    """An answer, as the person who gives it gives it.

    Raises:
        ValueError: If the digest isn't a SHA-256.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    approved: bool
    """Whether it approves the call."""
    arguments_digest: str
    """The digest of the arguments the person was shown; an answer to others is refused."""
    surface: str
    """The surface it was given on, such as ``portalr``, :data:`CONFIRM_SURFACE` or ``mcp``."""
    reason: str | None = None
    """Why, in the person's words, if they gave one."""
    scope: AnswerScope | None = None
    """How far it stands beyond its call, from the scopes the request offered, if at all."""

    @model_validator(mode="after")
    def _well_formed(self) -> Self:
        _digest(self.arguments_digest, "an answer's arguments digest")
        return self


class Answered(Answer):
    """An answer as the store records it: who gave it, and when."""

    by: Subject
    """Who answered."""
    at: AwareDatetime
    """When it was answered."""


class Approval(ApprovalRequest):
    """An approval, asked: its request, where it stands, and its answer or why it closed.

    Raises:
        ValueError: If its answer or reason doesn't fit its state: an answer exactly when it is
            approved or denied, agreeing with it, and a reason exactly when it expired or was
            withdrawn; or it was taken without being approved.
    """

    id: ApprovalId
    """Its id."""
    asked_at: AwareDatetime
    """When it was asked."""
    state: State
    """Where it stands."""
    answer: Answered | None = None
    """The answer that settled it, if one did."""
    reason: str | None = None
    """Why it expired or was withdrawn."""
    taken_at: AwareDatetime | None = None
    """When the one call it lets through went ahead, if one has: an approval is for one call."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        answered = self.state in ("approved", "denied")
        if answered != (self.answer is not None):
            raise ValueError(f"an approval {self.state} has an answer exactly when answered")
        if self.answer is not None and self.answer.approved != (self.state == "approved"):
            raise ValueError(f"an approval {self.state} can't carry that answer")
        if (self.state in ("expired", "withdrawn")) != (self.reason is not None):
            raise ValueError(f"an approval {self.state} has a reason exactly when it closed")
        if self.taken_at is not None and self.state != "approved":
            raise ValueError(f"an approval {self.state} lets no call through")
        return self


class ApprovalError(Exception):
    """An approval's store refused what was asked of it."""


class UnknownApproval(ApprovalError, LookupError):
    """No approval of the id.

    Args:
        id: The id asked for.
    """

    def __init__(self, id: ApprovalId) -> None:
        super().__init__(f"no approval {id}")
        self.id = id


class NotPending(ApprovalError):
    """The approval isn't pending any more, so it takes no answer and can't be withdrawn.

    Args:
        approval: The approval as it stands.
    """

    def __init__(self, approval: Approval, message: str | None = None) -> None:
        super().__init__(message or f"approval {approval.id} is {approval.state}")
        self.approval = approval


class AlreadyAnswered(NotPending):
    """Someone answered first; their answer stands, and every surface shows it.

    Args:
        approval: The approval, with the first answer.
        first: The first answer, the approval's.
    """

    def __init__(self, approval: Approval, first: Answered) -> None:
        super().__init__(
            approval,
            f"approval {approval.id} was {approval.state} by {first.by.id} on {first.surface} "
            f"at {first.at.isoformat()}",
        )
        self.first = first


class NotApproved(ApprovalError):
    """The approval lets no call through: it isn't approved, or its one call went ahead already.

    Args:
        approval: The approval as it stands.
    """

    def __init__(self, approval: Approval) -> None:
        taken = approval.taken_at
        super().__init__(
            f"approval {approval.id} let its one call through at {taken.isoformat()}"
            if taken is not None
            else f"approval {approval.id} is {approval.state}"
        )
        self.approval = approval


class DigestMismatch(ApprovalError):
    """The answer was given to other arguments than those the approval asks about."""


class ScopeNotOffered(ApprovalError):
    """The answer's scope names a pattern the request didn't offer."""


class NotAnAnswerer(ApprovalError):
    """The subject may not answer the approval, or not on that surface."""


@runtime_checkable
class Approvals(Protocol):
    """Where approvals are asked, answered, withdrawn and watched: grantr's store, or a fake.

    ``answer`` is a compare-and-set on a pending approval, in one transaction with its audit
    entry: the first answer wins, and the others get :class:`AlreadyAnswered` with it. ``take``
    is one on an approved approval not yet taken: an approval lets one call through.
    """

    async def ask(self, request: ApprovalRequest, /) -> Approval:
        """Ask an approval, pending, and return it."""
        ...

    async def get(self, id: ApprovalId, /) -> Approval:
        """Return the approval as it stands.

        Raises:
            UnknownApproval: If there is no approval of the id.
        """
        ...

    async def answer(self, id: ApprovalId, answer: Answer, /, *, subject: Subject) -> Approval:
        """Answer a pending approval as the subject, and return it settled.

        Raises:
            UnknownApproval: If there is no approval of the id.
            AlreadyAnswered: If someone answered first.
            NotPending: If it expired or was withdrawn.
            NotAnAnswerer: If the subject may not answer it, or not on that surface.
            DigestMismatch: If the answer was given to other arguments.
            ScopeNotOffered: If the answer's scope names a pattern the request didn't offer.
        """
        ...

    async def take(self, id: ApprovalId, /) -> Approval:
        """Take an approved approval for the one call it lets through, and return it, taken.

        Of calls that go ahead on it at once, exactly one takes it.

        Raises:
            UnknownApproval: If there is no approval of the id.
            NotApproved: If it isn't approved, or was taken already.
        """
        ...

    async def withdraw(self, id: ApprovalId, reason: str, /) -> Approval:
        """Withdraw a pending approval, because its run stopped or its arguments changed.

        Raises:
            UnknownApproval: If there is no approval of the id.
            NotPending: If it is settled already.
        """
        ...

    async def pending(self, scope: Scope, subject: Subject, /) -> list[Approval]:
        """Return the approvals pending in the scope that the subject may answer."""
        ...

    def watch(self, id: ApprovalId, /) -> AsyncIterator[Approval]:
        """Yield the approval as it stands, then each change, until it is settled.

        Raises:
            UnknownApproval: If there is no approval of the id.
        """
        ...


@runtime_checkable
class ApprovalPolicy(Protocol):
    """Whether a call needs a person's approval, and whose.

    It decides from the capability's tier and risk class, the taint step's ``ask``, and the
    settings: the operator sets the floor, and a tenant or workspace may ask approval on more
    tiers, never on fewer.
    """

    async def needed(self, capability: Capability, context: CallContext, /) -> Answerers | None:
        """Return who must approve the call, or None if it needs no approval."""
        ...


@runtime_checkable
class Coverage(Protocol):
    """Whether an approved plan already covers a call, so the enforcer asks no new approval.

    reflexr answers it inside the run's transaction: an approved plan approval of the run whose
    ``covers`` lists the call's step with its digest unchanged, the arguments within its target,
    calls left, and the run's budget and window not passed. It records the use. Never a call
    that taint asks about, nor one that needs a different approver than the plan's.
    """

    async def cover(
        self, context: CallContext, capability: Capability, arguments: JsonObject, /
    ) -> ApprovalId | None:
        """Return the id of the approval that covers the call, or None to ask anew."""
        ...


class NoCoverage:
    """The coverage of an application without plans: it covers nothing, so every call asks."""

    async def cover(
        self, _context: CallContext, _capability: Capability, _arguments: JsonObject, /
    ) -> ApprovalId | None:
        """Return None: nothing is covered."""
        return None


@runtime_checkable
class ApprovalSurface(Protocol):
    """Somewhere approvals are offered to the people who may answer them, such as portalr.

    The store offers each new approval to the surfaces of the subjects who may answer it, and
    tells each surface it offered one on when it is settled. A different approver's approval is
    never offered to the caller's surfaces.
    """

    async def offer(self, approval: Approval, /, *, to: frozenset[str]) -> None:
        """Offer the approval to the subjects of the ids."""
        ...

    async def resolved(self, approval: Approval, /) -> None:
        """Say that an approval it was offered is settled."""
        ...


def _holds_nothing(_subject: Subject, _action: str, /) -> bool:
    """Whether a subject holds an action: no one holds any."""
    return False


class FakeApprovals:
    """An in-memory store of approvals for tests, with the semantics grantr's store keeps.

    The first answer wins; an answer must carry the digest it was shown and a scope from those
    offered; an approved approval is taken once. A subject answers when named, in a group named,
    or holding the action, which ``holds`` decides; a different approver is never the person who
    asked; a confirmation is answered only by its subject, on :data:`CONFIRM_SURFACE`, and never
    by a service principal.
    Nothing expires on its own: :meth:`expire_due` is the sweep, by the clock given.

    Args:
        holds: Whether a subject holds a grantr action; no one holds any if omitted.
        clock: The time now; the system's, in UTC, if omitted.
    """

    def __init__(
        self,
        *,
        holds: Callable[[Subject, str], bool] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._holds = holds or _holds_nothing
        self._clock = clock or (lambda: datetime.now(UTC))
        self._ids = count(1)
        self._approvals: dict[ApprovalId, Approval] = {}
        self._changed: dict[ApprovalId, asyncio.Condition] = {}
        self._lock = asyncio.Lock()

    def _get(self, id: ApprovalId) -> Approval:
        try:
            return self._approvals[id]
        except KeyError:
            raise UnknownApproval(id) from None

    async def _settle(self, approval: Approval) -> Approval:
        self._approvals[approval.id] = approval
        changed = self._changed[approval.id]
        async with changed:
            changed.notify_all()
        return approval

    def may_answer(self, approval: Approval, subject: Subject) -> bool:
        """Whether the subject may answer the approval, on some surface."""
        answerers = approval.answerers
        if answerers.different_approver and subject.id == _person(approval.asked_by):
            return False
        if answerers.confirmation:
            return not subject.service and subject.id in answerers.subjects
        return (
            subject.id in answerers.subjects
            or bool(subject.groups & answerers.groups)
            or (answerers.action is not None and self._holds(subject, answerers.action))
        )

    async def ask(self, request: ApprovalRequest, /) -> Approval:
        """Ask an approval, pending, and return it."""
        async with self._lock:
            approval = Approval(
                **dict(request),
                id=f"apr_{next(self._ids)}",
                asked_at=self._clock(),
                state="pending",
            )
            self._approvals[approval.id] = approval
            self._changed[approval.id] = asyncio.Condition()
            return approval

    async def get(self, id: ApprovalId, /) -> Approval:
        """Return the approval as it stands.

        Raises:
            UnknownApproval: If there is no approval of the id.
        """
        return self._get(id)

    async def answer(self, id: ApprovalId, answer: Answer, /, *, subject: Subject) -> Approval:
        """Answer a pending approval as the subject, and return it settled.

        Raises:
            UnknownApproval: If there is no approval of the id.
            AlreadyAnswered: If someone answered first.
            NotPending: If it expired or was withdrawn.
            NotAnAnswerer: If the subject may not answer it, or not on that surface.
            DigestMismatch: If the answer was given to other arguments.
            ScopeNotOffered: If the answer's scope names a pattern the request didn't offer.
        """
        async with self._lock:
            approval = self._get(id)
            if approval.answer is not None:
                raise AlreadyAnswered(approval, approval.answer)
            if approval.state != "pending":
                raise NotPending(approval)
            if not self.may_answer(approval, subject):
                raise NotAnAnswerer(f"{subject.id} may not answer approval {id}")
            if approval.answerers.confirmation and answer.surface != CONFIRM_SURFACE:
                raise NotAnAnswerer(f"approval {id} is confirmed on {CONFIRM_SURFACE} alone")
            if answer.arguments_digest != approval.arguments_digest:
                raise DigestMismatch(f"approval {id} asks about other arguments")
            if answer.scope is not None and (
                unoffered := set(answer.scope.patterns) - set(approval.scopes_offered)
            ):
                raise ScopeNotOffered(f"approval {id} offers no scope {sorted(unoffered)}")
            answered = Answered(**dict(answer), by=subject, at=self._clock())
            state: State = "approved" if answer.approved else "denied"
            return await self._settle(
                approval.model_copy(update={"state": state, "answer": answered})
            )

    async def take(self, id: ApprovalId, /) -> Approval:
        """Take an approved approval for the one call it lets through, and return it, taken.

        Raises:
            UnknownApproval: If there is no approval of the id.
            NotApproved: If it isn't approved, or was taken already.
        """
        async with self._lock:
            approval = self._get(id)
            if approval.state != "approved" or approval.taken_at is not None:
                raise NotApproved(approval)
            taken = approval.model_copy(update={"taken_at": self._clock()})
            self._approvals[id] = taken
            return taken

    async def withdraw(self, id: ApprovalId, reason: str, /) -> Approval:
        """Withdraw a pending approval, because its run stopped or its arguments changed.

        Raises:
            UnknownApproval: If there is no approval of the id.
            NotPending: If it is settled already.
        """
        async with self._lock:
            approval = self._get(id)
            if approval.state != "pending":
                raise NotPending(approval)
            return await self._settle(
                approval.model_copy(update={"state": "withdrawn", "reason": reason})
            )

    async def expire_due(self) -> list[Approval]:
        """Expire every pending approval past its deadline, and return them: the sweep."""
        async with self._lock:
            now = self._clock()
            due = [
                approval
                for approval in self._approvals.values()
                if approval.state == "pending" and approval.deadline <= now
            ]
            return [
                await self._settle(
                    approval.model_copy(
                        update={"state": "expired", "reason": "past its deadline unanswered"}
                    )
                )
                for approval in due
            ]

    async def pending(self, scope: Scope, subject: Subject, /) -> list[Approval]:
        """Return the approvals pending in the scope that the subject may answer, oldest first."""
        return [
            approval
            for approval in self._approvals.values()
            if approval.state == "pending"
            and approval.scope == scope
            and self.may_answer(approval, subject)
        ]

    async def watch(self, id: ApprovalId, /) -> AsyncIterator[Approval]:
        """Yield the approval as it stands, then each change, until it is settled.

        Raises:
            UnknownApproval: If there is no approval of the id.
        """
        approval = self._get(id)
        changed = self._changed[id]
        yield approval
        while approval.state == "pending":
            async with changed:
                await changed.wait_for(partial(self._moved, approval))
            approval = self._approvals[id]
            yield approval

    def _moved(self, seen: Approval) -> bool:
        """Whether the approval has changed since it was seen."""
        return self._approvals[seen.id] is not seen

    def all(self) -> Iterable[Approval]:
        """Return every approval it holds, in the order asked."""
        return tuple(self._approvals.values())


class _Contract(BaseModel):
    approval: Approval
    answer: Answer


def contract_schema() -> dict[str, JsonValue]:
    """Return the contract's JSON Schema: an approval, as asked and settled, and an answer."""
    schema = _Contract.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"lattice.approvals {CONTRACT}",
        "description": (
            "lattice's approval contract: `approval` is one call asked of the people who may "
            "answer it, with its request, its state and its answer, and `answer` what one of "
            "them gives."
        ),
        "type": "object",
        "properties": schema["properties"],
        "$defs": schema["$defs"],
    }
