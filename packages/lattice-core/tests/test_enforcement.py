"""The enforcement path: nine steps in order, each a port, every call audited, approvals asked
and resumed, a plan's coverage, and taint marked even when the provider raised (RFC-0011)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from lattice_core.approvals import (
    Answer,
    Answerers,
    FakeApprovals,
    NoCoverage,
    Subject,
    arguments_digest,
)
from lattice_core.capabilities import (
    TIERS,
    CallContext,
    Capability,
    FakeProvider,
    Gate,
    JsonObject,
    PersonCaller,
    Registry,
    RunCaller,
    Scope,
    SessionCaller,
    ToolResult,
)
from lattice_core.enforcement import (
    STEPS,
    ApprovalClosed,
    ApprovalPending,
    Called,
    CallFailed,
    Enforcer,
    FakeAudit,
    FakeCounter,
    FixedCeilings,
    FixedTaint,
    Forbidden,
    LimitReached,
    NotEnabled,
    Step,
    TaintDenied,
    TierRefused,
    UnknownCapability,
    WrongApproval,
)
from lattice_core.integrations import Defaults, Integration
from lattice_core.settings import IntRange, Setting, SettingsDefaults, Subset
from lattice_core.taint import Cause, Clean, Tainted

HERE = Scope(tenant_id="acme", workspace_id="docs")
NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)
ARGUMENTS: JsonObject = {"to": "finance@example.com"}
GITHUB = Integration(key="mcp:github", default=False, description="GitHub's MCP server.")
WIKI = Integration(key="wiki", default=True, description="The wiki.")
PER_HOUR = Setting(
    key="calls-per-hour:mail",
    kind=IntRange(0, 100),
    default=2,
    lowest="workspace",
    description="Mails an hour.",
)
NAMES = Setting(
    key="mail:domains",
    kind=Subset(frozenset({"example.com"})),
    default=("example.com",),
    lowest="workspace",
    description="Domains mail goes to.",
)
EARLIER = datetime(2026, 10, 31, 11, tzinfo=UTC)
TAINTED = Tainted(causes=(Cause(capability="web.fetch", at=EARLIER),), seen_hosts=frozenset({"a"}))


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def capability(name: str = "mail.send", **changes: Any) -> Capability:
    fields: dict[str, Any] = {
        "name": name,
        "version": "1.0.0",
        "description": "Send a mail.",
        "input_schema": {"type": "object"},
        "output_schema": None,
        "provider": "builtin",
        "tier": "outbound",
        "effects": frozenset({"sends_out"}),
        "reversibility": "irreversible",
        "gate": Gate(integration=None, action="mail:send"),
    }
    return Capability.model_validate(fields | changes)


def context(**changes: Any) -> CallContext:
    fields: dict[str, Any] = {
        "scope": HERE,
        "caller": RunCaller(id="run_1", agent="mailer", on_behalf_of="alex"),
        "taint": Clean(),
        "correlation_id": "run_1",
        "surface": "portalr",
    }
    return CallContext.model_validate(fields | changes)


class Policy:
    """An approval policy that asks the answerers it is given, for every call."""

    def __init__(self, answerers: Answerers | None = None) -> None:
        self.answerers = answerers

    async def needed(self, _capability: Capability, _context: CallContext, /) -> Answerers | None:
        return self.answerers


class Covers:
    """A plan's coverage that covers every call with one approval, and records being asked."""

    def __init__(self, covered: str | None = "apr_plan") -> None:
        self.covered = covered
        self.asked = 0

    async def cover(self, _c: CallContext, _cap: Capability, _a: JsonObject, /) -> str | None:
        self.asked += 1
        return self.covered


class Broken:
    """A counter, or settings, that can't be read."""

    async def count(self, _key: str, _context: CallContext, /) -> int:
        raise ConnectionError("down")

    async def value(self, _t: str, _w: str, _key: str, /) -> int:
        raise ConnectionError("down")


class Built:
    """An enforcer of fakes, with what a test inspects."""

    def __init__(
        self,
        *capabilities: Capability,
        results: dict[str, ToolResult | Exception] | None = None,
        allowed: bool = True,
        **ports: Any,
    ) -> None:
        self.provider = FakeProvider("builtin", *capabilities, results=results)
        self.audit = FakeAudit()
        self.store = FakeApprovals(clock=Clock())
        self.clock = Clock()
        self.granted: list[str] = []

        async def authorize(_context: CallContext, action: str) -> bool:
            self.granted.append(action)
            return allowed

        defaults: dict[str, Any] = {
            "integrations": Defaults({GITHUB.key: GITHUB, WIKI.key: WIKI}),
            "authorize": authorize,
            "ceilings": FixedCeilings(),
            "settings": SettingsDefaults({PER_HOUR.key: PER_HOUR, NAMES.key: NAMES}),
            "counter": FakeCounter(),
            "taint": FixedTaint(),
            "approvals": Policy(),
            "coverage": NoCoverage(),
            "store": self.store,
            "audit": self.audit,
            "clock": self.clock,
        }
        self.enforcer = Enforcer(Registry(self.provider), **(defaults | ports))

    async def call(self, name: str = "mail.send", **changes: Any) -> Called:
        approval = changes.pop("approval", None)
        arguments = changes.pop("arguments", ARGUMENTS)
        return await self.enforcer.call(name, arguments, context(**changes), approval=approval)

    def steps(self) -> list[tuple[str, bool]]:
        return [(step.name, step.passed) for step in self.audit.entries[-1].steps]


# ─── Every step passed ────────────────────────────────────────────────────────


async def test_a_call_passes_every_step_in_order_and_is_audited() -> None:
    built = Built(capability(), results={"mail.send": ToolResult(output="sent")})
    called = await built.call()
    assert called == Called(result=ToolResult(output="sent"), taint=Clean())
    assert built.steps() == [(step, True) for step in STEPS]
    [entry] = built.audit.entries
    assert (entry.capability, entry.version, entry.outcome, entry.approval) == (
        "mail.send",
        "1.0.0",
        "called",
        None,
    )
    assert (entry.caller, entry.on_behalf_of, entry.correlation_id, entry.surface) == (
        "run:run_1",
        "alex",
        "run_1",
        "portalr",
    )
    assert (entry.arguments_digest, entry.at, entry.scope) == (
        arguments_digest(ARGUMENTS),
        NOW,
        HERE,
    )
    assert built.granted == ["mail:send"]
    [call] = built.provider.calls
    assert call.arguments == ARGUMENTS


async def test_the_default_clock_is_the_systems_in_utc() -> None:
    audit = FakeAudit()
    enforcer = Enforcer(
        Registry(FakeProvider("builtin", capability())),
        integrations=Defaults({}),
        authorize=_yes,
        ceilings=FixedCeilings(),
        settings=SettingsDefaults({}),
        counter=FakeCounter(),
        taint=FixedTaint(),
        approvals=Policy(),
        coverage=NoCoverage(),
        store=FakeApprovals(),
        audit=audit,
    )
    await enforcer.call("mail.send", ARGUMENTS, context())
    assert abs(datetime.now(UTC) - audit.entries[0].at) < timedelta(minutes=1)


async def _yes(_context: CallContext, _action: str) -> bool:
    return True


# ─── Steps 0 to 4 ─────────────────────────────────────────────────────────────


async def test_an_unknown_capability_is_refused_and_still_audited() -> None:
    built = Built(capability())
    with pytest.raises(UnknownCapability, match=r"no capability mail\.delete") as refused:
        await built.call("mail.delete")
    assert refused.value.step == "registry"
    [entry] = built.audit.entries
    assert (entry.version, entry.outcome) == (None, "refused")
    assert built.steps() == [("registry", False), ("audit", True)]


async def test_an_integration_off_is_not_enabled_before_any_grant_is_asked() -> None:
    built = Built(capability(gate=Gate(integration="mcp:github", action="mcp:create_issue")))
    with pytest.raises(NotEnabled, match="mcp:github is off"):
        await built.call()
    assert built.granted == [], "off before forbidden"
    assert built.steps() == [("integration", False), ("audit", True)]
    on = Built(capability(gate=Gate(integration="wiki", action="wiki:edit")))
    assert await on.call()


async def test_a_caller_without_the_grant_is_forbidden() -> None:
    built = Built(capability(), allowed=False)
    with pytest.raises(Forbidden, match="mail:send"):
        await built.call()
    assert built.steps() == [("integration", True), ("grant", False), ("audit", True)]


async def test_an_agents_run_is_refused_a_tier_above_its_ceiling_and_people_are_not() -> None:
    built = Built(capability(), ceilings=FixedCeilings(frozenset({"read", "write"})))
    with pytest.raises(TierRefused, match="mailer may not call outbound tools"):
        await built.call()
    assert await built.call(caller=PersonCaller(id="alex"))
    assert await built.call(caller=SessionCaller(id="s_1", on_behalf_of="alex"))


async def test_a_limit_is_counted_per_call_and_refuses_past_its_value() -> None:
    built = Built(capability(limits=(PER_HOUR.key,)))
    await built.call()
    await built.call()
    with pytest.raises(LimitReached, match="calls-per-hour:mail is reached"):
        await built.call()


@pytest.mark.parametrize(
    ("ports", "says"),
    [
        ({"counter": Broken()}, "couldn't be read: ConnectionError"),
        ({"settings": Broken()}, "couldn't be read: ConnectionError"),
        ({"settings": SettingsDefaults({})}, "couldn't be read: KeyError"),
    ],
)
async def test_a_limit_that_cant_be_read_or_counted_refuses(
    ports: dict[str, Any], says: str
) -> None:
    built = Built(capability(limits=(PER_HOUR.key,)), **ports)
    with pytest.raises(LimitReached, match=says) as refused:
        await built.call()
    assert isinstance(refused.value.__cause__, ConnectionError | KeyError)


async def test_a_limit_whose_setting_isnt_a_number_refuses() -> None:
    built = Built(capability(limits=(NAMES.key,)))
    with pytest.raises(LimitReached, match="mail:domains is reached"):
        await built.call()


# ─── Step 5: taint ────────────────────────────────────────────────────────────


async def test_a_taint_that_denies_refuses_and_one_that_narrows_goes_ahead() -> None:
    denied = Built(capability(), taint=FixedTaint("deny"))
    with pytest.raises(TaintDenied, match="refuses it"):
        await denied.call(taint=TAINTED)
    assert await denied.call(), "a clean caller is allowed"
    narrowed = Built(capability(), taint=FixedTaint("narrow"))
    assert await narrowed.call(taint=TAINTED)
    taint_step = narrowed.audit.entries[-1].steps[4]
    assert (taint_step.name, taint_step.note) == ("taint", "narrow")


async def test_a_taint_that_asks_asks_the_person_the_run_acts_for() -> None:
    built = Built(capability(), taint=FixedTaint("ask"), coverage=Covers())
    with pytest.raises(ApprovalPending) as pending:
        await built.call(taint=TAINTED)
    asked = await built.store.get(pending.value.approval)
    assert asked.answerers == Answerers(subjects=frozenset({"alex"}))


async def test_a_taint_that_asks_with_no_one_to_ask_refuses() -> None:
    built = Built(capability(), taint=FixedTaint("ask"))
    with pytest.raises(TaintDenied, match="needs a person"):
        await built.call(taint=TAINTED, caller=RunCaller(id="run_2", agent="rules"))


async def test_a_taint_that_asks_keeps_the_policys_answerers_and_is_never_covered() -> None:
    coverage = Covers()
    sam = Answerers(subjects=frozenset({"sam"}))
    built = Built(capability(), taint=FixedTaint("ask"), approvals=Policy(sam), coverage=coverage)
    with pytest.raises(ApprovalPending) as pending:
        await built.call(taint=TAINTED)
    assert (await built.store.get(pending.value.approval)).answerers == sam
    assert coverage.asked == 0, "the person approved the plan before the untrusted content"


# ─── Step 6: approval ─────────────────────────────────────────────────────────


async def test_a_call_that_needs_approval_waits_and_goes_ahead_once_approved() -> None:
    sam = Answerers(subjects=frozenset({"sam"}))
    built = Built(
        capability(),
        approvals=Policy(sam),
        approve_within=timedelta(hours=2),
        results={"mail.send": ToolResult(output="sent")},
    )
    with pytest.raises(ApprovalPending, match="waits for approval apr_1") as pending:
        await built.call()
    approval = await built.store.get(pending.value.approval)
    assert (approval.capability, approval.version, approval.deadline) == (
        "mail.send",
        "1.0.0",
        NOW + timedelta(hours=2),
    )
    assert approval.rendering.title == "Send a mail."
    assert approval.rendering.arguments == ARGUMENTS
    assert (approval.asked_by, approval.answerers) == (context().caller, sam)
    entry = built.audit.entries[-1]
    assert (entry.outcome, entry.approval) == ("pending", "apr_1")
    assert built.steps()[-2:] == [("approval", False), ("audit", True)]
    assert built.provider.calls == []

    with pytest.raises(ApprovalPending):
        await built.call(approval="apr_1")
    answer = Answer(approved=True, arguments_digest=arguments_digest(ARGUMENTS), surface="portalr")
    await built.store.answer("apr_1", answer, subject=Subject(id="sam"))
    called = await built.call(approval="apr_1")
    assert (called.result.output, called.approval) == ("sent", "apr_1")
    assert built.audit.entries[-1].approval == "apr_1"


async def test_an_approval_lets_one_call_through() -> None:
    built = Built(capability(), approvals=Policy(Answerers(subjects=frozenset({"sam"}))))
    with pytest.raises(ApprovalPending):
        await built.call()
    yes = Answer(approved=True, arguments_digest=arguments_digest(ARGUMENTS), surface="portalr")
    await built.store.answer("apr_1", yes, subject=Subject(id="sam"))
    await built.call(approval="apr_1")
    with pytest.raises(ApprovalClosed, match="apr_1 let its one call through at "):
        await built.call(approval="apr_1")
    assert len(built.provider.calls) == 1
    assert (await built.store.get("apr_1")).taken_at == NOW


async def test_a_call_resumed_on_its_approval_was_counted_as_it_asked() -> None:
    counter = FakeCounter()
    built = Built(
        capability(limits=(PER_HOUR.key,)),
        approvals=Policy(Answerers(subjects=frozenset({"sam"}))),
        counter=counter,
        settings=SettingsDefaults({PER_HOUR.key: PER_HOUR}, {PER_HOUR.key: 1}),
    )
    with pytest.raises(ApprovalPending):
        await built.call()
    yes = Answer(approved=True, arguments_digest=arguments_digest(ARGUMENTS), surface="portalr")
    await built.store.answer("apr_1", yes, subject=Subject(id="sam"))
    await built.call(approval="apr_1")
    assert counter.counts == {(PER_HOUR.key, HERE): 1}
    assert built.audit.entries[-1].steps[3] == Step(
        name="limits", passed=True, note="counted as it asked approval"
    )
    with pytest.raises(LimitReached):
        await built.call()


async def test_a_denied_or_closed_approval_refuses() -> None:
    built = Built(capability(), approvals=Policy(Answerers(subjects=frozenset({"sam"}))))
    with pytest.raises(ApprovalPending):
        await built.call()
    no = Answer(approved=False, arguments_digest=arguments_digest(ARGUMENTS), surface="mcp")
    await built.store.answer("apr_1", no, subject=Subject(id="sam"))
    with pytest.raises(ApprovalClosed, match="apr_1 is denied"):
        await built.call(approval="apr_1")


async def test_an_approval_for_another_call_is_refused() -> None:
    built = Built(capability(), capability("mail.draft"), approvals=Policy(Answerers(action="x:y")))
    with pytest.raises(ApprovalPending):
        await built.call()
    with pytest.raises(WrongApproval):
        await built.call(approval="apr_1", arguments={"to": "everyone@example.com"})
    with pytest.raises(WrongApproval):
        await built.call("mail.draft", approval="apr_1")


async def test_a_plan_that_covers_the_call_lets_it_go_ahead_without_asking() -> None:
    coverage = Covers()
    built = Built(capability(), approvals=Policy(Answerers(action="x:y")), coverage=coverage)
    called = await built.call()
    assert called.approval == "apr_plan"
    assert list(built.store.all()) == []
    assert coverage.asked == 1


@pytest.mark.parametrize(
    "answerers",
    [
        Answerers(action="x:y", different_approver=True),
        Answerers(subjects=frozenset({"alex"}), confirmation=True),
    ],
)
async def test_a_plan_never_covers_a_different_approver_or_a_confirmation(
    answerers: Answerers,
) -> None:
    coverage = Covers()
    built = Built(capability(), approvals=Policy(answerers), coverage=coverage)
    with pytest.raises(ApprovalPending):
        await built.call(caller=PersonCaller(id="alex"))
    assert coverage.asked == 0


async def test_a_plan_that_doesnt_cover_the_call_lets_it_ask() -> None:
    coverage = Covers(covered=None)
    built = Built(capability(), approvals=Policy(Answerers(action="x:y")), coverage=coverage)
    with pytest.raises(ApprovalPending):
        await built.call()
    assert coverage.asked == 1


# ─── Steps 7 and 8: the call, and taint marked ────────────────────────────────


async def test_a_capability_that_reads_untrusted_content_taints_the_caller() -> None:
    fetch = capability("web.fetch", tier="read", effects=frozenset({"reads_untrusted"}))
    built = Built(fetch)
    clean = await built.call("web.fetch")
    assert clean.taint == Tainted(causes=(Cause(capability="web.fetch", at=NOW),))
    again = await built.call("web.fetch", taint=TAINTED)
    assert again.taint == Tainted(
        causes=(*TAINTED.causes, Cause(capability="web.fetch", at=NOW)),
        seen_hosts=TAINTED.seen_hosts,
    )
    assert (await built.call("web.fetch", taint=TAINTED)).taint != TAINTED
    assert built.audit.entries[0].steps[7].note == "tainted"


async def test_a_capability_that_reads_nothing_untrusted_leaves_the_taint_as_it_was() -> None:
    built = Built(capability())
    assert (await built.call(taint=TAINTED)).taint == TAINTED


async def test_a_provider_that_raises_is_marked_audited_and_carried_with_its_taint() -> None:
    fetch = capability("web.fetch", tier="read", effects=frozenset({"reads_untrusted"}))
    built = Built(fetch, results={"web.fetch": TimeoutError("slow")})
    with pytest.raises(CallFailed, match="TimeoutError: slow") as failed:
        await built.call("web.fetch")
    assert isinstance(failed.value.__cause__, TimeoutError)
    assert failed.value.error is failed.value.__cause__
    assert failed.value.taint == Tainted(causes=(Cause(capability="web.fetch", at=NOW),))
    entry = built.audit.entries[-1]
    assert entry.outcome == "failed"
    assert built.steps() == [(step, True) for step in STEPS]


# ─── The fakes ────────────────────────────────────────────────────────────────


async def test_the_fake_counter_counts_per_limit_and_scope() -> None:
    counter = FakeCounter()
    there = context(scope=Scope(tenant_id="acme", workspace_id="ops"))
    assert [await counter.count("a", context()) for _ in range(2)] == [1, 2]
    assert await counter.count("a", there) == 1
    assert await counter.count("b", context()) == 1


async def test_the_fixed_ceiling_is_every_tier_unless_given() -> None:
    assert await FixedCeilings().tiers("any", HERE) == frozenset(TIERS)
    assert await FixedCeilings(frozenset({"read"})).tiers("any", HERE) == {"read"}


async def test_fixed_taint_allows_a_clean_caller_whatever_it_answers_a_tainted_one() -> None:
    policy = FixedTaint("deny")
    assert await policy.decide(capability(), Clean(), HERE) == "allow"
    assert await policy.decide(capability(), TAINTED, HERE) == "deny"
    assert await FixedTaint().decide(capability(), TAINTED, HERE) == "allow"
