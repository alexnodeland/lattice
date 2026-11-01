"""The enforcement path: the only way a capability is called (lattice RFC-0011).

:class:`Enforcer` calls a capability by name, for a :class:`~lattice_core.capabilities.CallContext`,
through nine steps in order, each answered by a port the application injects:

1. **Integration on?** The capability's gate's integration, through
   :class:`~lattice_core.integrations.Integrations`; off is :class:`NotEnabled`, never forbidden.
2. **Allowed?** The gate's grantr action, through :class:`Authorize`; grantr answers it, and
   lattice-core never imports grantr.
3. **Tier allowed for this agent?** An agent's run is refused a tier outside its ceiling
   (:class:`Ceilings`).
4. **Limits.** Each setting the capability names in ``limits`` is read through
   :class:`~lattice_core.settings.Settings` and counted by a :class:`Counter`; a limit that can't
   be read or counted refuses.
5. **Taint.** :class:`TaintPolicy` answers ``allow``, ``narrow``, ``ask`` or ``deny``.
6. **Approval.** The :class:`~lattice_core.approvals.ApprovalPolicy` says who must approve, if
   anyone; a taint ``ask`` needs someone too. The :class:`~lattice_core.approvals.Coverage` is asked
   first whether an approved plan covers the call; otherwise an approval is asked of the
   :class:`~lattice_core.approvals.Approvals` store, open for the workspace's ``approve-within``
   minutes, and the call is deferred (:class:`ApprovalPending`) until it is answered, and called
   again with its id.
7. **Call** the provider.
8. **Mark taint:** a capability that ``reads_untrusted`` taints the caller, even when it raised,
   which comes back as :class:`CallFailed` with the taint.
9. **Audit:** one :class:`CapabilityCalled` entry for every call, refused or not, through
   :class:`Audit`.

A refusal at a step raises its :class:`Refused` and stops there; later steps don't run. The
enforcer holds no state: the taint a call leaves is returned in :class:`Called`, for the caller to
carry to its next call.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Final, Literal, Protocol, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict

from lattice_core.approvals import (
    Answerers,
    ApprovalId,
    ApprovalPolicy,
    ApprovalRequest,
    Approvals,
    Coverage,
    NotApproved,
    Rendering,
    arguments_digest,
)
from lattice_core.capabilities import (
    TIERS,
    CallContext,
    Capability,
    JsonObject,
    PersonCaller,
    Registry,
    RunCaller,
    Scope,
    Tier,
    ToolResult,
    Via,
)
from lattice_core.integrations import Integrations
from lattice_core.settings import APPROVE_WITHIN, Settings
from lattice_core.taint import Cause, Clean, Taint, Tainted

__all__ = [
    "STEPS",
    "ApprovalClosed",
    "ApprovalPending",
    "Audit",
    "Authorize",
    "CallFailed",
    "Called",
    "CapabilityCalled",
    "Ceilings",
    "Counter",
    "Enforcer",
    "FakeAudit",
    "FakeCounter",
    "FixedCeilings",
    "FixedTaint",
    "Forbidden",
    "LimitReached",
    "NotEnabled",
    "Outcome",
    "Refused",
    "Step",
    "StepName",
    "TaintDenied",
    "TaintPolicy",
    "TaintVerdict",
    "TierRefused",
    "UnknownCapability",
    "WrongApproval",
]

StepName = Literal[
    "registry",
    "integration",
    "grant",
    "tier",
    "limits",
    "taint",
    "approval",
    "call",
    "mark",
    "audit",
]
"""A step of the enforcement path, or ``registry``, where a name no capability has is refused
before the first."""

STEPS: Final[tuple[StepName, ...]] = (
    "integration",
    "grant",
    "tier",
    "limits",
    "taint",
    "approval",
    "call",
    "mark",
    "audit",
)
"""The steps, in the order they run."""

TaintVerdict = Literal["allow", "narrow", "ask", "deny"]
"""What a taint policy answers for a call: go ahead, go ahead narrowed (egress decides how), ask a
person first, or refuse."""

Outcome = Literal["called", "failed", "refused", "pending"]
"""How a call ended: the provider answered, the provider raised, a step refused it, or it waits
for an approval."""


# ─── Ports ────────────────────────────────────────────────────────────────────


type Authorize = Callable[[CallContext, str], Awaitable[bool]]
"""Whether the caller, in the call's scope, holds a grantr action: grantr answers it. The context
carries the caller, the scope and the outside client the call came through, if any."""


@runtime_checkable
class Ceilings(Protocol):
    """The tiers an agent's runs may call in a scope: its ceiling, narrowed per workspace."""

    async def tiers(self, agent: str, scope: Scope, /) -> frozenset[Tier]:
        """Return the tiers the agent may call in the scope."""
        ...


@runtime_checkable
class Counter(Protocol):
    """Counts a call against a limit, and says how many it has counted in the limit's window."""

    async def count(self, key: str, context: CallContext, /) -> int:
        """Count this call against a limit, and return the calls counted, this one included.

        It may count per scope, per caller or per outside client (``context.via``).
        """
        ...


@runtime_checkable
class TaintPolicy(Protocol):
    """What a workspace allows a caller with its taint to call (#903)."""

    async def decide(self, capability: Capability, taint: Taint, scope: Scope, /) -> TaintVerdict:
        """Return whether the call goes ahead, narrowed, after a person's approval, or not."""
        ...


@runtime_checkable
class Audit(Protocol):
    """Where every call's entry is recorded: grantr's audit log."""

    async def record(self, entry: "CapabilityCalled", /) -> None:
        """Record the entry."""
        ...


# ─── What a call leaves ───────────────────────────────────────────────────────


class Step(BaseModel):
    """A step a call passed or was stopped at, as the audit records it."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    name: StepName
    """The step."""
    passed: bool
    """Whether the call went on past it."""
    note: str = ""
    """What it decided, in words, where there is more to say: a taint verdict, an approval's id."""


class CapabilityCalled(BaseModel):
    """One call of a capability, as the audit records it: never its arguments or its output."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    capability: str
    """The name asked for."""
    version: str | None
    """The version called, or None if no capability of the name was offered."""
    scope: Scope
    """Where it was called."""
    caller: str
    """Who called, as ``kind:id``, such as ``run:run_1``."""
    on_behalf_of: str | None
    """The person the caller acts for, if any."""
    via: Via | None
    """The outside client it came through, if any."""
    correlation_id: str
    """The id of the turn, run or session that made it."""
    surface: str
    """The surface it came from."""
    arguments_digest: str
    """The digest of its arguments, which an approval binds to."""
    steps: tuple[Step, ...]
    """Each step it passed, and the one that stopped it, in order."""
    outcome: Outcome
    """How it ended."""
    approval: ApprovalId | None = None
    """The approval that let it go ahead, or that it waits for."""
    at: AwareDatetime
    """When it was called."""


class Called(BaseModel):
    """What a call returned, and the caller's taint after it."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    result: ToolResult
    """The provider's answer."""
    taint: Taint
    """The caller's taint now, marked if the capability reads untrusted content."""
    approval: ApprovalId | None = None
    """The approval that let it go ahead, if one did: asked for it, or a plan's that covers it."""


# ─── Refusals ─────────────────────────────────────────────────────────────────


class Refused(Exception):
    """A step refused the call.

    Args:
        step: The step that refused it.
        message: Why, for the caller and the audit.
    """

    def __init__(self, step: StepName, message: str) -> None:
        super().__init__(message)
        self.step: StepName = step


class UnknownCapability(Refused):
    """No capability of the name is offered in the scope."""


class NotEnabled(Refused):
    """The capability's integration is off in the workspace."""


class Forbidden(Refused):
    """The caller doesn't hold the capability's grantr action."""


class TierRefused(Refused):
    """The capability's tier is above the agent's ceiling."""


class LimitReached(Refused):
    """A limit is reached, or couldn't be read or counted."""


class TaintDenied(Refused):
    """The caller's taint refuses the call, or needs a person and there is none to ask."""


class ApprovalPending(Refused):
    """The call waits for an approval; call again with its id once it is answered.

    Args:
        approval: The approval's id.
    """

    def __init__(self, approval: ApprovalId) -> None:
        super().__init__("approval", f"waits for approval {approval}")
        self.approval = approval


class ApprovalClosed(Refused):
    """The approval was denied, expired or was withdrawn."""


class WrongApproval(Refused):
    """The approval given is for another capability or other arguments."""


class CallFailed(Exception):
    """The provider raised: its error, as the cause, and the caller's taint after the call.

    Args:
        error: What the provider raised.
        taint: The caller's taint now, marked if the capability reads untrusted content.
    """

    def __init__(self, error: Exception, taint: Taint) -> None:
        super().__init__(f"the call failed: {type(error).__name__}: {error}")
        self.error = error
        self.taint: Taint = taint


# ─── The enforcer ─────────────────────────────────────────────────────────────


def _person(context: CallContext) -> str | None:
    caller = context.caller
    return caller.id if isinstance(caller, PersonCaller) else caller.on_behalf_of


def _mark(taint: Taint, capability: Capability, at: datetime) -> Taint:
    """Return the taint after a call: tainted by the capability if it reads untrusted content."""
    if "reads_untrusted" not in capability.effects:
        return taint
    cause = Cause(capability=capability.name, at=at)
    if isinstance(taint, Clean):
        return Tainted(causes=(cause,))
    return Tainted(causes=(*taint.causes, cause), seen_hosts=taint.seen_hosts)


class Enforcer:
    """Calls capabilities through the nine steps, each a port the application injects.

    Args:
        registry: The capabilities, composed.
        integrations: Whether an integration is on in a workspace.
        authorize: Whether a caller holds a grantr action.
        ceilings: The tiers an agent may call.
        settings: The limits' values.
        counter: Counts calls against limits.
        taint: What a caller's taint allows.
        approvals: Who must approve a call.
        coverage: Whether an approved plan covers a call.
        store: Where approvals are asked and read.
        audit: Where each call is recorded.
        approve_within: How long a new approval stays open where ``settings`` doesn't declare
            ``approve-within``: a day, if omitted. Where it does, the workspace's value, in
            minutes, says.
        clock: The time now; the system's, in UTC, if omitted.
    """

    def __init__(
        self,
        registry: Registry,
        *,
        integrations: Integrations,
        authorize: Authorize,
        ceilings: Ceilings,
        settings: Settings,
        counter: Counter,
        taint: TaintPolicy,
        approvals: ApprovalPolicy,
        coverage: Coverage,
        store: Approvals,
        audit: Audit,
        approve_within: timedelta = timedelta(days=1),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.registry = registry
        self._integrations = integrations
        self._authorize = authorize
        self._ceilings = ceilings
        self._settings = settings
        self._counter = counter
        self._taint = taint
        self._approvals = approvals
        self._coverage = coverage
        self._store = store
        self._audit = audit
        self._within = approve_within
        self._clock = clock or (lambda: datetime.now(UTC))

    async def call(
        self,
        name: str,
        arguments: JsonObject,
        context: CallContext,
        *,
        approval: ApprovalId | None = None,
    ) -> Called:
        """Call a capability by name, through every step, and record it.

        Args:
            name: The capability's name.
            arguments: Its arguments.
            context: Who calls, where, with what taint, from where.
            approval: The approval an earlier call of these arguments waited for, now answered.

        Raises:
            Refused: The step that refused it, as one of its subclasses: :class:`ApprovalPending`
                when it waits for an approval.
            CallFailed: If the provider raised, with the caller's taint, marked, and the error
                as its cause.
        """
        at = self._clock()
        digest = arguments_digest(arguments)
        steps: list[Step] = []
        found = self.registry.find(context.scope, name)
        capability = found.capability if found else None
        outcome: Outcome = "refused"
        allowed: ApprovalId | None = approval
        try:
            if found is None:
                raise UnknownCapability("registry", f"no capability {name} in this workspace")
            await self._check(found.capability, context, steps, resumed=approval is not None)
            verdict = await self._taint_step(found.capability, context, steps)
            allowed = await self._approval_step(
                found.capability, arguments, digest, context, verdict, approval, steps
            )
            outcome = "failed"
            try:
                result = await found.provider.call(found.capability, arguments, context)
            except Exception as error:
                marked = self._marked(found.capability, context, steps)
                raise CallFailed(error, marked) from error
            marked = self._marked(found.capability, context, steps)
            outcome = "called"
            return Called(result=result, taint=marked, approval=allowed)
        except ApprovalPending as pending:
            outcome, allowed = "pending", pending.approval
            steps.append(Step(name="approval", passed=False, note=f"waits for {pending.approval}"))
            raise
        except Refused as refused:
            steps.append(Step(name=refused.step, passed=False, note=str(refused)))
            raise
        finally:
            steps.append(Step(name="audit", passed=True))
            await self._audit.record(
                CapabilityCalled(
                    capability=name,
                    version=capability.version if capability else None,
                    scope=context.scope,
                    caller=f"{context.caller.kind}:{context.caller.id}",
                    on_behalf_of=_person(context),
                    via=context.via,
                    correlation_id=context.correlation_id,
                    surface=context.surface,
                    arguments_digest=digest,
                    steps=tuple(steps),
                    outcome=outcome,
                    approval=allowed,
                    at=at,
                )
            )

    def _marked(self, capability: Capability, context: CallContext, steps: list[Step]) -> Taint:
        """Steps 7 and 8, once the provider answered or raised: the caller's taint, marked."""
        steps.append(Step(name="call", passed=True))
        marked = _mark(context.taint, capability, self._clock())
        steps.append(Step(name="mark", passed=True, note=marked.state))
        return marked

    async def _check(
        self, capability: Capability, context: CallContext, steps: list[Step], *, resumed: bool
    ) -> None:
        """Steps 1 to 4: the integration, the grant, the tier and the limits.

        A try is counted once, when first made: a call resumed on an approval was counted as it
        asked for it, and its approval lets one call through.
        """
        scope, gate = context.scope, capability.gate
        if gate.integration is not None and not await self._integrations.is_enabled(
            scope.tenant_id, scope.workspace_id, gate.integration
        ):
            raise NotEnabled("integration", f"{gate.integration} is off in this workspace")
        steps.append(Step(name="integration", passed=True))
        if not await self._authorize(context, gate.action):
            raise Forbidden("grant", f"the caller doesn't hold {gate.action}")
        steps.append(Step(name="grant", passed=True))
        caller = context.caller
        if isinstance(caller, RunCaller):
            ceiling = await self._ceilings.tiers(caller.agent, scope)
            if capability.tier not in ceiling:
                raise TierRefused("tier", f"{caller.agent} may not call {capability.tier} tools")
        steps.append(Step(name="tier", passed=True))
        if resumed and capability.limits:
            steps.append(Step(name="limits", passed=True, note="counted as it asked approval"))
            return
        for key in capability.limits:
            try:
                limit = await self._settings.value(scope.tenant_id, scope.workspace_id, key)
                counted = await self._counter.count(key, context)
            except Exception as error:  # a limit that can't be read or counted refuses
                message = f"{key} couldn't be read: {type(error).__name__}"
                raise LimitReached("limits", message) from error
            if not isinstance(limit, int) or counted > limit:
                raise LimitReached("limits", f"{key} is reached")
        steps.append(Step(name="limits", passed=True))

    async def _taint_step(
        self, capability: Capability, context: CallContext, steps: list[Step]
    ) -> TaintVerdict:
        """Step 5: what the caller's taint allows."""
        verdict = await self._taint.decide(capability, context.taint, context.scope)
        if verdict == "deny":
            raise TaintDenied("taint", "the caller's taint refuses it")
        steps.append(Step(name="taint", passed=True, note=verdict))
        return verdict

    async def _approval_step(
        self,
        capability: Capability,
        arguments: JsonObject,
        digest: str,
        context: CallContext,
        verdict: TaintVerdict,
        approval: ApprovalId | None,
        steps: list[Step],
    ) -> ApprovalId | None:
        """Step 6: an approval answered, a plan that covers the call, or a new approval."""
        if approval is not None:
            await self._answered(approval, capability, digest, context)
            steps.append(Step(name="approval", passed=True, note=approval))
            return approval
        answerers = await self._approvals.needed(capability, context)
        if verdict == "ask" and answerers is None:
            person = _person(context)
            if person is None:
                raise TaintDenied("taint", "the caller's taint needs a person, and there is none")
            answerers = Answerers(subjects=frozenset({person}))
        if answerers is None:
            steps.append(Step(name="approval", passed=True, note="not needed"))
            return None
        if (
            verdict != "ask"
            and not answerers.different_approver
            and not answerers.confirmation
            and (covered := await self._coverage.cover(context, capability, arguments))
        ):
            steps.append(Step(name="approval", passed=True, note=f"covered by {covered}"))
            return covered
        asked = await self._store.ask(
            ApprovalRequest(
                scope=context.scope,
                capability=capability.name,
                version=capability.version,
                rendering=Rendering(title=capability.description, arguments=arguments),
                arguments_digest=digest,
                asked_by=context.caller,
                via=context.via,
                answerers=answerers,
                deadline=self._clock() + await self._open_for(context.scope),
            )
        )
        raise ApprovalPending(asked.id)

    async def _open_for(self, scope: Scope) -> timedelta:
        """How long a new approval stays open: the workspace's ``approve-within``, in minutes.

        Where the settings don't declare it, the enforcer's own ``approve_within``.

        Raises:
            TypeError: If the setting isn't a whole number, which refuses the call.
        """
        try:
            minutes = await self._settings.value(
                scope.tenant_id, scope.workspace_id, APPROVE_WITHIN
            )
        except KeyError:
            return self._within
        if not isinstance(minutes, int):
            raise TypeError(f"{APPROVE_WITHIN} is a number of minutes, not {minutes!r}")
        return timedelta(minutes=minutes)

    async def _answered(
        self, id: ApprovalId, capability: Capability, digest: str, context: CallContext
    ) -> None:
        """Check that an approval given is this call's and approved, and take it for the call.

        This call's is one asked for this capability and these arguments, in this scope, by this
        caller, through this client: an id from another tenant's, another person's or another
        client's call lets nothing through, however it was answered.
        """
        approval = await self._store.get(id)
        if approval.capability != capability.name or approval.arguments_digest != digest:
            raise WrongApproval("approval", f"approval {id} is for another call")
        if (approval.scope, approval.asked_by, approval.via) != (
            context.scope,
            context.caller,
            context.via,
        ):
            raise WrongApproval("approval", f"approval {id} was asked by another caller")
        if approval.state == "pending":
            raise ApprovalPending(id)
        try:
            await self._store.take(id)
        except NotApproved as closed:
            raise ApprovalClosed("approval", str(closed)) from closed


# ─── Fakes, for tests ─────────────────────────────────────────────────────────


class FakeAudit:
    """An audit that keeps every entry in :attr:`entries`, in order."""

    def __init__(self) -> None:
        self.entries: list[CapabilityCalled] = []
        """Every entry recorded, in order."""

    async def record(self, entry: CapabilityCalled, /) -> None:
        """Keep the entry."""
        self.entries.append(entry)


class FakeCounter:
    """Counts every call against each limit, per scope, with no window: it never forgets."""

    def __init__(self) -> None:
        self.counts: dict[tuple[str, Scope], int] = {}
        """The calls counted, by limit and scope."""

    async def count(self, key: str, context: CallContext, /) -> int:
        """Count the call, and return the calls counted against the limit in its scope."""
        place = (key, context.scope)
        self.counts[place] = self.counts.get(place, 0) + 1
        return self.counts[place]


class FixedCeilings:
    """The same ceiling for every agent, everywhere: every tier, if none is given.

    Args:
        tiers: The tiers every agent may call.
    """

    def __init__(self, tiers: frozenset[Tier] = frozenset(TIERS)) -> None:
        self._tiers = tiers

    async def tiers(self, _agent: str, _scope: Scope, /) -> frozenset[Tier]:
        """Return the ceiling."""
        return self._tiers


class FixedTaint:
    """The same verdict for a tainted caller everywhere, and ``allow`` for a clean one.

    Args:
        tainted: What a tainted caller is answered.
    """

    def __init__(self, tainted: TaintVerdict = "allow") -> None:
        self._tainted: TaintVerdict = tainted

    async def decide(self, _capability: Capability, taint: Taint, _scope: Scope, /) -> TaintVerdict:
        """Return ``allow`` for a clean caller, and the verdict given for a tainted one."""
        return self._tainted if isinstance(taint, Tainted) else "allow"
