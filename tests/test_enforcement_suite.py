"""The enforcement suite: every provider's capabilities, called only through the enforcer.

lattice RFC-0011's one suite for all providers. Tiers, grants, limits, taint, approvals and audit
run against a fake provider of each kind, and against each library's real provider, here since
it spans libraries. Phase 2's exit is that it passes on a fake and on artifactr's provider: a
covered call asks nothing, and each case a pre-approval never covers asks (artifactr ADR-0099,
lattice ADR-0037).

Each subject offers a ``read`` and a ``write`` capability. A write's effect is counted from the
provider's own state: a fake's calls, or the artifacts in artifactr's workspace. So "refused"
means the provider never heard of it.
"""

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic_ai import (
    Agent,
    DeferredToolRequests,
    DeferredToolResults,
    ModelMessage,
    ModelResponse,
    RunContext,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from artifactr.capabilities import ArtifactrProvider
from artifactr.core import ExternalAgentActor, MarkdownArtifact, UserActor
from artifactr.workspace import InMemoryStorage, Workspaces
from lattice_core.agents import APPROVAL, toolset
from lattice_core.approvals import (
    Answer,
    Answerers,
    ApprovalId,
    FakeApprovals,
    NoCoverage,
    Subject,
    arguments_digest,
)
from lattice_core.capabilities import (
    PROVIDER_KINDS,
    TIERS,
    CallContext,
    Capability,
    FakeProvider,
    Gate,
    JsonObject,
    Provider,
    ProviderKind,
    Registry,
    RunCaller,
    Scope,
    Tier,
    ToolResult,
)
from lattice_core.enforcement import (
    STEPS,
    ApprovalClosed,
    ApprovalPending,
    Called,
    Enforcer,
    FakeAudit,
    FakeCounter,
    FixedCeilings,
    FixedTaint,
    Forbidden,
    LimitReached,
    Refused,
    TaintDenied,
    TaintVerdict,
    TierRefused,
    WrongApproval,
)
from lattice_core.integrations import Defaults
from lattice_core.settings import IntRange, Setting, SettingsDefaults
from lattice_core.taint import Cause, Clean, Taint, Tainted

HERE = Scope(tenant_id="acme", workspace_id="docs")
NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)
TAINTED = Tainted(causes=(Cause(capability="web.fetch", at=NOW),))
PER_HOUR = Setting(
    key="calls-per-hour:suite",
    kind=IntRange(0, 100),
    default=1,
    lowest="workspace",
    description="A fake write's calls an hour.",
)


class Memo(MarkdownArtifact, name="suite_memo"):
    """A memo: the kind artifactr's provider creates here."""


# ─── the subjects ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Under:
    """A provider under the suite, with a read and a write of its own."""

    provider: Provider
    read: str
    read_arguments: JsonObject
    write: str
    write_arguments: JsonObject
    other_arguments: JsonObject
    """A write's arguments that aren't ``write_arguments``, for an approval given to another."""
    writes: Callable[[], Awaitable[int]]
    """How many of its writes took effect."""


def _fake(kind: ProviderKind) -> Under:
    def capability(name: str, **changes: Any) -> Capability:
        fields: dict[str, Any] = {
            "name": f"{kind}.{name}",
            "version": "1.0.0",
            "description": f"A fake {kind} {name}.",
            "input_schema": {"type": "object"},
            "output_schema": None,
            "provider": kind,
            "tier": "read",
            "effects": frozenset[str](),
            "reversibility": "none",
            "gate": Gate(integration=None, action=f"suite:{name}"),
        }
        return Capability.model_validate(fields | changes)

    read = capability("read", effects=frozenset({"reads_untrusted"}))
    write = capability("write", tier="write", limits=(PER_HOUR.key,), reversibility="undoable")
    provider = FakeProvider(kind, read, write, results={read.name: ToolResult(output="a page")})

    async def writes() -> int:
        return sum(1 for call in provider.calls if call.capability.name == write.name)

    return Under(provider, read.name, {}, write.name, {"to": "a"}, {"to": "b"}, writes)


def _artifactr() -> Under:
    workspaces = Workspaces(InMemoryStorage(), types=[Memo])
    provider = ArtifactrProvider(workspaces, types=[Memo])

    async def writes() -> int:
        workspace = await workspaces.open("acme", "docs", actor=UserActor(id="alex"))
        return len(await workspace.artifacts())

    return Under(
        provider,
        "artifactr.list_artifacts",
        {},
        "artifactr.create_artifact",
        {"kind": "suite_memo", "data": {"text": "Ship on Friday"}},
        {"kind": "suite_memo", "data": {"text": "Ship on Monday"}},
        writes,
    )


SUBJECTS: dict[str, Callable[[], Under]] = {
    **{f"fake {kind}": (lambda kind=kind: _fake(kind)) for kind in PROVIDER_KINDS},
    "artifactr": _artifactr,
}
"""Every subject, by name: a fake of each kind, and each library's provider."""


# ─── the world each case runs in ──────────────────────────────────────────────


class Policy:
    """An approval policy that asks the answerers given of every write, and of no read."""

    def __init__(self, answerers: Answerers | None) -> None:
        self.answerers = answerers

    async def needed(self, capability: Capability, _context: CallContext, /) -> Answerers | None:
        return self.answerers if capability.tier == "write" else None


class Plan:
    """Coverage by an approved plan: it covers every call it's asked about, and counts them."""

    def __init__(self) -> None:
        self.asked = 0

    async def cover(
        self, _context: CallContext, _capability: Capability, _arguments: JsonObject, /
    ) -> ApprovalId | None:
        self.asked += 1
        return "apr_plan"


@dataclass
class World:
    """An enforcer over one subject, and the fakes around it."""

    under: Under
    allowed: bool = True
    ceiling: frozenset[Tier] = frozenset(TIERS)
    tainted: TaintVerdict = "allow"
    answerers: Answerers | None = None
    coverage: Plan | NoCoverage = field(default_factory=NoCoverage)
    store: FakeApprovals = field(default_factory=FakeApprovals)
    audit: FakeAudit = field(default_factory=FakeAudit)
    counter: FakeCounter = field(default_factory=FakeCounter)

    def enforcer(self) -> Enforcer:
        async def authorize(_context: CallContext, _action: str) -> bool:
            return self.allowed

        return Enforcer(
            Registry(self.under.provider),
            integrations=Defaults({}),
            authorize=authorize,
            ceilings=FixedCeilings(self.ceiling),
            settings=SettingsDefaults({PER_HOUR.key: PER_HOUR}),
            counter=self.counter,
            taint=FixedTaint(self.tainted),
            approvals=Policy(self.answerers),
            coverage=self.coverage,
            store=self.store,
            audit=self.audit,
            clock=lambda: NOW,
        )

    async def read(self, taint: Taint | None = None) -> Called:
        under = self.under
        return await self.enforcer().call(under.read, under.read_arguments, context(taint))

    async def write(self, taint: Taint | None = None, approval: ApprovalId | None = None) -> Called:
        under = self.under
        within = context(taint)
        return await self.enforcer().call(
            under.write, under.write_arguments, within, approval=approval
        )

    async def answer(self, approval: ApprovalId, by: str, *, approved: bool = True) -> None:
        digest = arguments_digest(self.under.write_arguments)
        answer = Answer(approved=approved, arguments_digest=digest, surface="portalr")
        await self.store.answer(approval, answer, subject=Subject(id=by))


def context(taint: Taint | None = None) -> CallContext:
    return CallContext(
        scope=HERE,
        caller=RunCaller(id="run_1", agent="helper", on_behalf_of="alex"),
        taint=taint or Clean(),
        correlation_id="run_1",
        surface="portalr",
    )


def run[T](case: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(case)


async def refused[E: Refused](kind: type[E], call: Awaitable[Called]) -> E:
    with pytest.raises(kind) as raised:
        await call
    return raised.value


subjects = pytest.mark.parametrize("subject", sorted(SUBJECTS))


# ─── the cases ────────────────────────────────────────────────────────────────


@subjects
def test_a_call_passes_every_step_in_order_and_is_audited(subject: str) -> None:
    async def case() -> None:
        world = World(SUBJECTS[subject]())
        await world.read()
        [entry] = world.audit.entries
        assert [step.name for step in entry.steps] == list(STEPS)
        assert (entry.outcome, entry.caller, entry.on_behalf_of) == ("called", "run:run_1", "alex")

    run(case())


@subjects
def test_a_write_past_the_agents_ceiling_is_refused_before_the_provider_hears_of_it(
    subject: str,
) -> None:
    async def case() -> None:
        world = World(SUBJECTS[subject](), ceiling=frozenset({"read"}))
        await refused(TierRefused, world.write())
        await world.read()
        assert await world.under.writes() == 0
        assert [entry.outcome for entry in world.audit.entries] == ["refused", "called"]

    run(case())


@subjects
def test_a_caller_without_the_grant_is_refused(subject: str) -> None:
    async def case() -> None:
        world = World(SUBJECTS[subject](), allowed=False)
        refusal = await refused(Forbidden, world.write())
        assert refusal.step == "grant"
        assert await world.under.writes() == 0

    run(case())


@subjects
def test_a_limit_declared_is_counted_and_refuses_past_its_value(subject: str) -> None:
    async def case() -> None:
        world = World(SUBJECTS[subject]())
        found = world.enforcer().registry.find(HERE, world.under.write)
        assert found is not None
        await world.write()
        if found.capability.limits:
            await refused(LimitReached, world.write())
            assert await world.under.writes() == 1
        else:
            await world.write()
            assert (await world.under.writes(), world.counter.counts) == (2, {})

    run(case())


@subjects
def test_a_call_leaves_its_caller_tainted_only_if_it_reads_untrusted_content(
    subject: str,
) -> None:
    async def case() -> None:
        world = World(SUBJECTS[subject]())
        called = await world.read()
        found = world.enforcer().registry.find(HERE, world.under.read)
        assert found is not None
        if "reads_untrusted" in found.capability.effects:
            assert called.taint == Tainted(
                causes=(Cause(capability=found.capability.name, at=NOW),)
            )
        else:
            assert called.taint == Clean()

    run(case())


@subjects
def test_taint_that_denies_refuses_and_taint_that_asks_asks_the_person(subject: str) -> None:
    async def case() -> None:
        denied = World(SUBJECTS[subject](), tainted="deny")
        await refused(TaintDenied, denied.write(TAINTED))
        asking = World(SUBJECTS[subject](), tainted="ask")
        pending = await refused(ApprovalPending, asking.write(TAINTED))
        approval = await asking.store.get(pending.approval)
        assert approval.answerers == Answerers(subjects=frozenset({"alex"}))
        assert await asking.under.writes() == 0
        await asking.answer(pending.approval, "alex")
        await asking.write(TAINTED, approval=pending.approval)
        assert await denied.under.writes() + await asking.under.writes() == 1

    run(case())


@subjects
def test_an_approval_holds_a_write_until_it_is_approved_for_its_arguments(subject: str) -> None:
    """Approved, it lets one call through, uncounted again by a limit it was counted against as
    it asked: a fake's write may be called once an hour."""

    async def case() -> None:
        sam = Answerers(subjects=frozenset({"sam"}))
        world = World(SUBJECTS[subject](), answerers=sam)
        pending = await refused(ApprovalPending, world.write())
        await refused(ApprovalPending, world.write(approval=pending.approval))
        assert await world.under.writes() == 0
        await world.answer(pending.approval, "sam")
        under = world.under
        other = world.enforcer().call(
            under.write, under.other_arguments, context(), approval=pending.approval
        )
        await refused(WrongApproval, other)
        called = await world.write(approval=pending.approval)
        assert called.approval == pending.approval
        await refused(ApprovalClosed, world.write(approval=pending.approval))
        assert await world.under.writes() == 1

    run(case())


@subjects
def test_a_denied_approval_refuses_its_call(subject: str) -> None:
    async def case() -> None:
        world = World(SUBJECTS[subject](), answerers=Answerers(subjects=frozenset({"sam"})))
        pending = await refused(ApprovalPending, world.write())
        await world.answer(pending.approval, "sam", approved=False)
        await refused(ApprovalClosed, world.write(approval=pending.approval))
        assert await world.under.writes() == 0

    run(case())


@subjects
def test_a_call_a_plan_covers_asks_nothing(subject: str) -> None:
    async def case() -> None:
        sam = Answerers(subjects=frozenset({"sam"}))
        world = World(SUBJECTS[subject](), answerers=sam, coverage=Plan())
        called = await world.write()
        assert called.approval == "apr_plan"
        assert (await world.under.writes(), list(world.store.all())) == (1, [])

    run(case())


@pytest.mark.parametrize(
    ("answerers", "tainted"),
    [
        (Answerers(subjects=frozenset({"sam"}), different_approver=True), "allow"),
        (Answerers(subjects=frozenset({"alex"}), confirmation=True), "allow"),
        (None, "ask"),
    ],
    ids=["a different approver", "a confirmation", "taint that asks"],
)
@subjects
def test_a_plan_never_covers_another_approver_a_confirmation_or_taint(
    subject: str, answerers: Answerers | None, tainted: TaintVerdict
) -> None:
    async def case() -> None:
        plan = Plan()
        world = World(SUBJECTS[subject](), answerers=answerers, tainted=tainted, coverage=plan)
        await refused(ApprovalPending, world.write(TAINTED))
        assert (plan.asked, await world.under.writes(), len(list(world.store.all()))) == (0, 0, 1)

    run(case())


@subjects
def test_every_call_refused_or_not_is_audited_once_by_its_arguments_digest(subject: str) -> None:
    async def case() -> None:
        world = World(SUBJECTS[subject](), answerers=Answerers(subjects=frozenset({"sam"})))
        await world.read()
        pending = await refused(ApprovalPending, world.write())
        world.allowed = False
        await refused(Forbidden, world.write())
        outcomes = [(entry.outcome, entry.approval) for entry in world.audit.entries]
        assert outcomes == [("called", None), ("pending", pending.approval), ("refused", None)]
        digest = arguments_digest(world.under.write_arguments)
        assert [entry.arguments_digest for entry in world.audit.entries[1:]] == [digest] * 2
        for entry in world.audit.entries:
            assert entry.steps[-1].name == "audit"

    run(case())


# ─── artifactr's provider, through the agents bridge ─────────────────────────


def test_an_agents_run_writes_through_the_enforcer_and_pauses_for_the_policys_approval() -> None:
    """artifactr ADR-0099: an approval the policy asks pauses the run as `requires_approval` does,
    and the write is attributed to the agent acting for the person."""

    async def case() -> None:
        workspaces = Workspaces(InMemoryStorage(), types=[Memo])
        world = World(
            Under(
                ArtifactrProvider(workspaces, types=[Memo]),
                "artifactr.list_artifacts",
                {},
                "artifactr.create_artifact",
                {},
                {},
                _never,
            ),
            answerers=Answerers(subjects=frozenset({"sam"})),
        )
        taint: list[Taint] = []

        async def within(_ctx: RunContext[None]) -> CallContext:
            return context()

        async def marked(_ctx: RunContext[None], left: Taint) -> None:
            taint.append(left)

        create = {"kind": "suite_memo", "data": {"text": "Ship on Friday"}}
        script = [
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="artifactr__create_artifact", args=create, tool_call_id="c1"
                    )
                ]
            ),
            ModelResponse(parts=[TextPart("Created.")]),
        ]

        def respond(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
            return script.pop(0)

        agent = Agent(
            FunctionModel(respond),
            deps_type=type(None),
            output_type=[str, DeferredToolRequests],
            toolsets=[toolset(world.enforcer(), within, marked)],
        )
        paused = await agent.run("Write the memo")
        assert isinstance(paused.output, DeferredToolRequests)
        approval = paused.output.metadata["c1"][APPROVAL]
        answer = Answer(approved=True, arguments_digest=arguments_digest(create), surface="portalr")
        await world.store.answer(approval, answer, subject=Subject(id="sam"))
        ws = await workspaces.open("acme", "docs", actor=UserActor(id="alex"))
        assert await ws.artifacts() == []
        resumed = await agent.run(
            message_history=paused.all_messages(),
            deferred_tool_results=DeferredToolResults(
                approvals={"c1": True}, metadata={"c1": {APPROVAL: approval}}
            ),
        )
        assert resumed.output == "Created."
        [memo] = await ws.artifacts()
        assert memo.updated_by == ExternalAgentActor(
            client_id="agent:helper", name="helper", on_behalf_of=UserActor(id="alex")
        )
        assert taint == [Clean()]

    run(case())


async def _never() -> int:
    raise AssertionError("not counted here")
