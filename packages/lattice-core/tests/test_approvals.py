"""Approvals: the object, bound to its arguments, answered once by someone who may, and the fake
store's semantics, which grantr's store keeps too (lattice RFC-0011)."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from lattice_core.approvals import (
    CONFIRM_SURFACE,
    CONTRACT,
    STATES,
    AlreadyAnswered,
    Answer,
    Answered,
    Answerers,
    AnswerScope,
    Approval,
    ApprovalPolicy,
    ApprovalRequest,
    Approvals,
    ApprovalSurface,
    Coverage,
    DigestMismatch,
    FakeApprovals,
    ListedAction,
    NoCoverage,
    NotAnAnswerer,
    NotApproved,
    NotPending,
    Rendering,
    ScopeNotOffered,
    Subject,
    UnknownApproval,
    arguments_digest,
    contract_schema,
)
from lattice_core.capabilities import (
    CallContext,
    Capability,
    Gate,
    JsonObject,
    PersonCaller,
    RunCaller,
    Scope,
    SessionCaller,
    Via,
)
from lattice_core.taint import Clean

HERE = Scope(tenant_id="acme", workspace_id="docs")
THERE = Scope(tenant_id="acme", workspace_id="ops")
NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)
ARGUMENTS: JsonObject = {"to": "finance@example.com", "report": "weekly"}
DIGEST = arguments_digest(ARGUMENTS)
ALEX = Subject(id="alex")
SAM = Subject(id="sam")
BOT = Subject(id="ci-bot", service=True)


class Clock:
    """A clock a test moves by hand."""

    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def capability(**changes: Any) -> Capability:
    fields: dict[str, Any] = {
        "name": "artifactr.send_report",
        "version": "1.2.0",
        "description": "Send a report by email.",
        "input_schema": {"type": "object"},
        "output_schema": None,
        "provider": "command",
        "tier": "outbound",
        "effects": frozenset({"sends_out"}),
        "reversibility": "irreversible",
        "gate": Gate(integration=None, action="artifactr:send_report"),
    }
    return Capability.model_validate(fields | changes)


def request(**changes: Any) -> ApprovalRequest:
    """Alex's run asks Sam to approve sending the weekly report, by the end of the day."""
    fields: dict[str, Any] = {
        "scope": HERE,
        "capability": "artifactr.send_report",
        "version": "1.2.0",
        "rendering": Rendering(title="Send the weekly report", arguments=ARGUMENTS),
        "arguments_digest": DIGEST,
        "asked_by": RunCaller(id="run_1", agent="reporter", on_behalf_of="alex"),
        "answerers": Answerers(subjects=frozenset({"sam"})),
        "deadline": NOW + timedelta(hours=8),
    }
    return ApprovalRequest.model_validate(fields | changes)


def answer(**changes: Any) -> Answer:
    fields: dict[str, Any] = {"approved": True, "arguments_digest": DIGEST, "surface": "portalr"}
    return Answer.model_validate(fields | changes)


def confirmation() -> ApprovalRequest:
    """Alex's own confirmation of an admin_high call Alex made."""
    return request(
        asked_by=PersonCaller(id="alex"),
        answerers=Answerers(subjects=frozenset({"alex"}), confirmation=True),
    )


# ─── The object ───────────────────────────────────────────────────────────────


def test_the_digest_of_equal_arguments_is_one_whatever_their_order() -> None:
    assert arguments_digest({"a": 1, "b": [1, "é"]}) == arguments_digest({"b": [1, "é"], "a": 1})
    assert arguments_digest({"a": 1}) != arguments_digest({"a": 2})
    assert len(DIGEST) == 64


def test_a_rendering_shows_a_title_and_a_diff_or_the_arguments() -> None:
    assert Rendering(title="Edit the plan", diff="-a\n+b\n").diff == "-a\n+b\n"
    with pytest.raises(ValidationError, match="needs a title"):
        Rendering(title=" ", arguments={})
    with pytest.raises(ValidationError, match="a diff or the arguments"):
        Rendering(title="Edit the plan", summary="it edits")


@pytest.mark.parametrize(
    "fields",
    [
        {"action": "grantr:answer_approval"},
        {"subjects": frozenset({"sam"})},
        {"groups": frozenset({"finance"})},
        {"subjects": frozenset({"alex"}), "confirmation": True},
    ],
)
def test_answerers_name_an_action_subjects_or_groups(fields: dict[str, Any]) -> None:
    assert Answerers.model_validate(fields)


@pytest.mark.parametrize(
    ("fields", "says"),
    [
        ({}, "name an action, subjects or groups"),
        ({"action": "answer"}, "package:action"),
        ({"subjects": frozenset({"a", "b"}), "confirmation": True}, "one subject"),
        ({"groups": frozenset({"g"}), "confirmation": True}, "one subject"),
        (
            {"subjects": frozenset({"a"}), "action": "grantr:x", "confirmation": True},
            "one subject",
        ),
        (
            {"subjects": frozenset({"a"}), "groups": frozenset({"g"}), "confirmation": True},
            "one subject",
        ),
        (
            {"subjects": frozenset({"a"}), "different_approver": True, "confirmation": True},
            "one subject",
        ),
    ],
)
def test_answerers_that_name_no_one_or_confirm_for_more_than_one_are_refused(
    fields: dict[str, Any], says: str
) -> None:
    with pytest.raises(ValidationError, match=says):
        Answerers.model_validate(fields)


def test_a_scope_names_a_pattern() -> None:
    assert AnswerScope(within="session", patterns=("git push",)).expires_at is None
    with pytest.raises(ValidationError):
        AnswerScope(within="run", patterns=())


def test_a_listed_actions_digest_changes_with_the_capability_and_what_it_allows() -> None:
    listed = ListedAction.of("send", capability(), target={"to": "finance@"}, max_calls=1)
    assert (listed.capability, listed.major, listed.tier) == (
        "artifactr.send_report",
        1,
        "outbound",
    )
    assert ListedAction.of("send", capability(), target={"to": "finance@"}, max_calls=1) == listed
    others = [
        ListedAction.of("send", capability(tier="write"), target={"to": "finance@"}, max_calls=1),
        ListedAction.of("send", capability(version="2.0.0"), target={"to": "finance@"}),
        ListedAction.of("send", capability(), target={"to": "finance@"}, max_calls=2),
        ListedAction.of("mail", capability(), target={"to": "finance@"}, max_calls=1),
        ListedAction.of("send", capability()),
    ]
    digests = {listed.digest, *(other.digest for other in others)}
    assert len(digests) == 6


@pytest.mark.parametrize(
    ("changes", "says"),
    [({"capability": "send"}, "provider.tool"), ({"digest": "abc"}, "SHA-256")],
)
def test_a_listed_action_needs_a_capabilitys_name_and_a_digest(
    changes: dict[str, Any], says: str
) -> None:
    fields = ListedAction.of("send", capability()).model_dump() | changes
    with pytest.raises(ValidationError, match=says):
        ListedAction.model_validate(fields)


@pytest.mark.parametrize(
    ("changes", "says"),
    [
        ({"capability": "send_report"}, "provider.tool"),
        ({"version": "1.2"}, "MAJOR.MINOR.PATCH"),
        ({"arguments_digest": "ABC"}, "SHA-256"),
        (
            {"answerers": Answerers(subjects=frozenset({"sam"}), confirmation=True)},
            "of the person who called",
        ),
        (
            {
                "asked_by": SessionCaller(id="s_1"),
                "answerers": Answerers(subjects=frozenset({"alex"}), confirmation=True),
            },
            "of the person who called",
        ),
    ],
)
def test_a_request_is_refused_when_malformed(changes: dict[str, Any], says: str) -> None:
    with pytest.raises(ValidationError, match=says):
        request(**changes)


def test_a_confirmation_is_asked_of_the_person_who_called_or_whom_a_run_acts_for() -> None:
    assert confirmation().answerers.confirmation
    run = RunCaller(id="run_1", agent="admin", on_behalf_of="alex")
    assert request(
        asked_by=run, answerers=Answerers(subjects=frozenset({"alex"}), confirmation=True)
    )


def test_an_answer_carries_a_digest() -> None:
    with pytest.raises(ValidationError, match="SHA-256"):
        answer(arguments_digest="not a digest")


def approval(**changes: Any) -> Approval:
    fields: dict[str, Any] = dict(request()) | {"id": "apr_1", "asked_at": NOW, "state": "pending"}
    return Approval.model_validate(fields | changes)


def answered(*, approved: bool = True) -> Answered:
    return Answered(**dict(answer(approved=approved)), by=SAM, at=NOW)


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"state": "approved", "answer": answered()},
        {"state": "denied", "answer": answered(approved=False)},
        {"state": "expired", "reason": "past its deadline unanswered"},
        {"state": "withdrawn", "reason": "the run stopped"},
        {"state": "approved", "answer": answered(), "taken_at": NOW},
    ],
)
def test_an_approvals_answer_and_reason_fit_its_state(changes: dict[str, Any]) -> None:
    assert approval(**changes)


@pytest.mark.parametrize(
    ("changes", "says"),
    [
        ({"answer": answered()}, "answer exactly when answered"),
        ({"state": "approved"}, "answer exactly when answered"),
        ({"state": "approved", "answer": answered(approved=False)}, "can't carry that answer"),
        ({"state": "denied", "answer": answered()}, "can't carry that answer"),
        ({"state": "expired"}, "reason exactly when it closed"),
        ({"reason": "why not"}, "reason exactly when it closed"),
        ({"taken_at": NOW}, "an approval pending lets no call through"),
    ],
)
def test_an_approval_whose_answer_or_reason_doesnt_fit_its_state_is_refused(
    changes: dict[str, Any], says: str
) -> None:
    with pytest.raises(ValidationError, match=says):
        approval(**changes)


def test_an_approval_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError):
        request(deadline=datetime(2026, 10, 31, 20))


def test_the_states_are_those_an_approval_may_be_in() -> None:
    assert STATES == ("pending", "approved", "denied", "expired", "withdrawn")


def test_the_refusals_say_what_and_carry_the_approval() -> None:
    assert str(UnknownApproval("apr_9")) == "no approval apr_9"
    expired = approval(state="expired", reason="past its deadline unanswered")
    assert str(NotPending(expired)) == "approval apr_1 is expired"
    settled = approval(state="approved", answer=answered())
    first = AlreadyAnswered(settled, answered())
    assert (
        str(first) == "approval apr_1 was approved by sam on portalr at 2026-10-31T12:00:00+00:00"
    )
    assert (first.approval, first.first) == (settled, answered())


# ─── The ports ────────────────────────────────────────────────────────────────


class Everyone:
    async def needed(self, _capability: Capability, _context: CallContext, /) -> Answerers:
        return Answerers(action="grantr:answer_approval")


class Silent:
    def __init__(self) -> None:
        self.offered: list[tuple[str, frozenset[str]]] = []

    async def offer(self, approval: Approval, /, *, to: frozenset[str]) -> None:
        self.offered.append((approval.id, to))

    async def resolved(self, approval: Approval, /) -> None:
        self.offered.append((approval.id, frozenset()))


async def test_the_ports_are_protocols_their_implementations_satisfy() -> None:
    context = CallContext(
        scope=HERE,
        caller=PersonCaller(id="alex"),
        taint=Clean(),
        correlation_id="turn_1",
        surface="portalr",
    )
    assert isinstance(FakeApprovals(), Approvals)
    assert isinstance(Everyone(), ApprovalPolicy)
    assert isinstance(Silent(), ApprovalSurface)
    assert isinstance(NoCoverage(), Coverage)
    assert await NoCoverage().cover(context, capability(), ARGUMENTS) is None
    assert await Everyone().needed(capability(), context) == Answerers(
        action="grantr:answer_approval"
    )
    surface = Silent()
    await surface.offer(approval(), to=frozenset({"sam"}))
    await surface.resolved(approval())
    assert surface.offered == [("apr_1", frozenset({"sam"})), ("apr_1", frozenset())]


# ─── The fake store ───────────────────────────────────────────────────────────


async def test_an_approval_is_asked_pending_with_an_id_and_the_time() -> None:
    store = FakeApprovals(clock=Clock())
    first, second = await store.ask(request()), await store.ask(request(scope=THERE))
    assert (first.id, first.state, first.asked_at, first.answer) == ("apr_1", "pending", NOW, None)
    assert second.id == "apr_2"
    assert store.all() == (first, second)


async def test_the_default_clock_is_the_systems_in_utc() -> None:
    asked = await FakeApprovals().ask(request())
    assert asked.asked_at.tzinfo is UTC
    assert abs(datetime.now(UTC) - asked.asked_at) < timedelta(minutes=1)


@pytest.mark.parametrize("approved", [True, False])
async def test_an_answer_settles_it_and_records_who_and_when(approved: bool) -> None:
    clock = Clock()
    store = FakeApprovals(clock=clock)
    asked = await store.ask(request())
    clock.now = NOW + timedelta(minutes=5)
    settled = await store.answer(asked.id, answer(approved=approved, reason="ok"), subject=SAM)
    assert settled.state == ("approved" if approved else "denied")
    assert settled.answer == Answered(
        **dict(answer(approved=approved, reason="ok")), by=SAM, at=clock.now
    )


async def test_the_first_answer_wins_and_the_others_are_told_it() -> None:
    store = FakeApprovals()
    asked = await store.ask(request(answerers=Answerers(groups=frozenset({"finance"}))))
    people = [Subject(id=f"p{n}", groups=frozenset({"finance"})) for n in range(20)]

    async def answer_as(person: Subject) -> Approval | AlreadyAnswered:
        try:
            return await store.answer(asked.id, answer(approved=False), subject=person)
        except AlreadyAnswered as late:
            return late

    results = await asyncio.gather(*(answer_as(person) for person in people))
    [won] = [result for result in results if isinstance(result, Approval)]
    late = [result for result in results if isinstance(result, AlreadyAnswered)]
    assert len(late) == 19
    assert all(refusal.first == won.answer for refusal in late)


async def test_an_unknown_or_closed_approval_takes_no_answer() -> None:
    store = FakeApprovals()
    with pytest.raises(UnknownApproval):
        await store.answer("apr_9", answer(), subject=SAM)
    asked = await store.ask(request())
    await store.withdraw(asked.id, "the run stopped")
    with pytest.raises(NotPending) as closed:
        await store.answer(asked.id, answer(), subject=SAM)
    assert not isinstance(closed.value, AlreadyAnswered)
    assert closed.value.approval.state == "withdrawn"


async def test_an_answer_to_other_arguments_is_refused() -> None:
    store = FakeApprovals()
    asked = await store.ask(request())
    everyone: JsonObject = {**ARGUMENTS, "to": "everyone@example.com"}
    other = arguments_digest(everyone)
    with pytest.raises(DigestMismatch):
        await store.answer(asked.id, answer(arguments_digest=other), subject=SAM)
    assert (await store.answer(asked.id, answer(), subject=SAM)).state == "approved"


async def test_a_scope_must_be_one_the_request_offered() -> None:
    store = FakeApprovals()
    plain = await store.ask(request())
    scope = AnswerScope(within="session", patterns=("git push",))
    with pytest.raises(ScopeNotOffered, match="git push"):
        await store.answer(plain.id, answer(scope=scope), subject=SAM)
    offering = await store.ask(request(scopes_offered=("git push", "git fetch")))
    settled = await store.answer(offering.id, answer(scope=scope), subject=SAM)
    assert settled.answer is not None
    assert settled.answer.scope == scope


async def test_who_may_answer_is_named_grouped_or_holds_the_action() -> None:
    store = FakeApprovals(holds=lambda subject, action: (subject.id, action) == ("kim", "x:y"))
    asked = await store.ask(
        request(
            answerers=Answerers(
                action="x:y", subjects=frozenset({"sam"}), groups=frozenset({"finance"})
            )
        )
    )
    for subject in (SAM, Subject(id="lee", groups=frozenset({"finance"})), Subject(id="kim")):
        assert store.may_answer(asked, subject)
    assert not store.may_answer(asked, Subject(id="max", groups=frozenset({"legal"})))
    with pytest.raises(NotAnAnswerer):
        await store.answer(asked.id, answer(), subject=Subject(id="max"))


async def test_without_holds_no_one_holds_an_action() -> None:
    store = FakeApprovals()
    asked = await store.ask(request(answerers=Answerers(action="grantr:answer_approval")))
    assert not store.may_answer(asked, SAM)


async def test_a_different_approver_is_never_the_person_who_asked() -> None:
    store = FakeApprovals()
    asked = await store.ask(
        request(answerers=Answerers(subjects=frozenset({"alex", "sam"}), different_approver=True))
    )
    assert not store.may_answer(asked, ALEX)
    assert store.may_answer(asked, SAM)
    assert await store.pending(HERE, ALEX) == []
    with pytest.raises(NotAnAnswerer):
        await store.answer(asked.id, answer(), subject=ALEX)


async def test_a_confirmation_is_the_callers_alone_on_the_confirm_page() -> None:
    store = FakeApprovals()
    asked = await store.ask(confirmation())
    assert not store.may_answer(asked, Subject(id="alex", service=True))
    assert not store.may_answer(asked, SAM)
    with pytest.raises(NotAnAnswerer, match=CONFIRM_SURFACE):
        await store.answer(asked.id, answer(surface="mcp"), subject=ALEX)
    confirmed = await store.answer(asked.id, answer(surface=CONFIRM_SURFACE), subject=ALEX)
    assert confirmed.state == "approved"


async def test_a_service_principal_answers_only_where_named() -> None:
    store = FakeApprovals()
    named = await store.ask(request(answerers=Answerers(subjects=frozenset({"ci-bot"}))))
    assert (await store.answer(named.id, answer(), subject=BOT)).state == "approved"


async def test_an_approved_approval_is_taken_once_for_the_one_call_it_lets_through() -> None:
    clock = Clock()
    store = FakeApprovals(clock=clock)
    asked = await store.ask(request())
    with pytest.raises(NotApproved, match="apr_1 is pending"):
        await store.take(asked.id)
    await store.answer(asked.id, answer(), subject=SAM)
    clock.now = NOW + timedelta(minutes=5)
    calls = await asyncio.gather(*(_taking(store, asked.id) for _ in range(20)))
    [taken] = [call for call in calls if isinstance(call, Approval)]
    assert (taken.state, taken.taken_at) == ("approved", clock.now)
    assert await store.get(asked.id) == taken
    refused = [call for call in calls if isinstance(call, NotApproved)]
    assert len(refused) == 19
    assert str(refused[0]) == f"approval apr_1 let its one call through at {clock.now.isoformat()}"
    assert refused[0].approval == taken
    with pytest.raises(UnknownApproval):
        await store.take("apr_9")


async def _taking(store: FakeApprovals, id: str) -> Approval | NotApproved:
    try:
        return await store.take(id)
    except NotApproved as refused:
        return refused


async def test_withdrawn_once_and_only_while_pending() -> None:
    store = FakeApprovals()
    asked = await store.ask(request())
    withdrawn = await store.withdraw(asked.id, "its arguments changed")
    assert (withdrawn.state, withdrawn.reason) == ("withdrawn", "its arguments changed")
    with pytest.raises(NotPending):
        await store.withdraw(asked.id, "again")
    with pytest.raises(UnknownApproval):
        await store.withdraw("apr_9", "never asked")


async def test_the_sweep_expires_what_is_past_its_deadline_and_nothing_else() -> None:
    clock = Clock()
    store = FakeApprovals(clock=clock)
    soon = await store.ask(request(deadline=NOW + timedelta(minutes=10)))
    later = await store.ask(request(deadline=NOW + timedelta(hours=8)))
    answered_soon = await store.ask(request(deadline=NOW + timedelta(minutes=10)))
    await store.answer(answered_soon.id, answer(), subject=SAM)
    assert await store.expire_due() == []
    clock.now = NOW + timedelta(minutes=10)
    [expired] = await store.expire_due()
    assert (expired.id, expired.state, expired.reason) == (
        soon.id,
        "expired",
        "past its deadline unanswered",
    )
    assert [approval.id for approval in await store.pending(HERE, SAM)] == [later.id]


async def test_pending_lists_the_scopes_open_approvals_the_subject_may_answer() -> None:
    store = FakeApprovals()
    mine = await store.ask(request())
    await store.ask(request(scope=THERE))
    await store.ask(request(answerers=Answerers(subjects=frozenset({"kim"}))))
    closed = await store.ask(request())
    await store.withdraw(closed.id, "the run stopped")
    assert await store.pending(HERE, SAM) == [mine]


async def test_watch_yields_the_approval_then_each_change_until_settled() -> None:
    store = FakeApprovals()
    asked = await store.ask(request())
    watching = store.watch(asked.id)
    assert await anext(watching) == asked

    async def next_change() -> Approval:
        return await anext(watching)

    waiting = asyncio.create_task(next_change())
    await asyncio.sleep(0)  # it waits for a change
    assert not waiting.done()
    settled = await store.answer(asked.id, answer(), subject=SAM)
    assert await asyncio.wait_for(waiting, 1) == settled
    with pytest.raises(StopAsyncIteration):
        await anext(watching)
    assert [approval async for approval in store.watch(asked.id)] == [settled]


async def test_watching_an_unknown_approval_is_refused() -> None:
    with pytest.raises(UnknownApproval):
        await anext(FakeApprovals().watch("apr_9"))


# ─── The contract ─────────────────────────────────────────────────────────────


def test_the_contracts_schema_names_its_version_and_holds_an_approval_and_an_answer() -> None:
    schema = contract_schema()
    assert schema["title"] == f"lattice.approvals {CONTRACT}"
    assert schema["properties"] == {
        "approval": {"$ref": "#/$defs/Approval"},
        "answer": {"$ref": "#/$defs/Answer"},
    }


def test_a_via_is_carried_on_the_request() -> None:
    via = Via(connection_id="conn_1", client_name="Alex via Claude", surface="mcp")
    assert request(via=via).via == via
