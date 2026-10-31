"""grantr's store of approvals over every storage (lattice RFC-0011, grantr ADR-0038).

Each test that takes ``storage`` runs against memory, SQLite, and PostgreSQL as its owner and as
a role its row-level security holds. The first answer wins under races on each of them; who may
answer is grantr's to decide, from its members, groups and grants; and an approval is its
tenant's alone.
"""

import asyncio
from datetime import datetime, timedelta

import pytest

from grantr.core import (
    ApprovalAnswered,
    ApprovalAsked,
    ApprovalClosed,
    AuditFilter,
    Group,
    Invalid,
    Resource,
    Role,
    ServicePrincipal,
    User,
)
from grantr.grants import Grants, InMemoryStorage, Storage
from grantr.grants.approvals import EXPIRED, GrantrApprovals
from lattice_core.approvals import (
    CONFIRM_SURFACE,
    AlreadyAnswered,
    Answer,
    Answerers,
    AnswerScope,
    Approval,
    ApprovalRequest,
    Approvals,
    DigestMismatch,
    NotAnAnswerer,
    NotApproved,
    NotPending,
    Rendering,
    ScopeNotOffered,
    Subject,
    UnknownApproval,
    arguments_digest,
)
from lattice_core.capabilities import Caller, JsonObject, PersonCaller, RunCaller, Scope
from tests.catalogs import ARTIFACTR, PORTALR, REFLEXR
from tests.grants.conftest import ALICE, NOW, ROOT

BOB = User(id="bob")
"""acme's w1's admin, who holds ``grantr:answer_approval`` there."""

CAROL = User(id="carol")
"""acme's w1's editor, for whom the run acts."""

ERIN = User(id="erin")
"""A member of acme in the approvers group, with no role in w1."""

DAVE = User(id="dave")
"""globex's owner, in no way acme's."""

BOT = ServicePrincipal(id="bot")
"""acme's service principal, in the approvers group."""

W1 = Resource(kind="workspace", workspace="w1")
APPROVERS = Group(id="approvers")
ARGUMENTS: JsonObject = {"artifact": "a1", "text": "hello"}
DIGEST = arguments_digest(ARGUMENTS)
RUN = RunCaller(id="run_1", agent="helper", on_behalf_of=CAROL.id)
BY_ACTION = Answerers(action="grantr:answer_approval")


class Clock:
    """The time now, which a test moves."""

    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


async def _grants(storage: Storage) -> Grants:
    grants = Grants(storage, catalogs=[ARTIFACTR, REFLEXR, PORTALR])
    await grants.first_operator(ROOT.id)
    await grants.create_tenant("acme", owner=ALICE.id, by=ROOT)
    for member in (BOB, CAROL, ERIN, BOT):
        await grants.add_member("acme", member, by=ALICE)
    await grants.grant("acme", "admin", on=W1, to=BOB, by=ALICE)
    await grants.grant("acme", "editor", on=W1, to=CAROL, by=ALICE)
    await grants.define_group("acme", APPROVERS, frozenset((ERIN, BOT)), by=ALICE)
    await grants.create_tenant("globex", owner=DAVE.id, by=ROOT)
    return grants


def _store(grants: Grants, clock: Clock) -> GrantrApprovals:
    return grants.approvals(clock=clock, poll=timedelta(milliseconds=5))


def _request(
    answerers: Answerers = BY_ACTION,
    *,
    tenant: str = "acme",
    workspace: str = "w1",
    asked_by: Caller = RUN,
    deadline: datetime = NOW + timedelta(hours=1),
) -> ApprovalRequest:
    return ApprovalRequest(
        scope=Scope(tenant_id=tenant, workspace_id=workspace),
        capability="artifactr.edit_text",
        version="1.0.0",
        rendering=Rendering(title="Edit a1", arguments=ARGUMENTS),
        arguments_digest=DIGEST,
        asked_by=asked_by,
        answerers=answerers,
        deadline=deadline,
    )


def _answer(*, approved: bool = True, surface: str = "portalr") -> Answer:
    return Answer(approved=approved, arguments_digest=DIGEST, surface=surface)


def _as(user: User | ServicePrincipal, *, groups: frozenset[str] = frozenset()) -> Subject:
    return Subject(id=user.id, service=isinstance(user, ServicePrincipal), groups=groups)


APPROVALS = AuditFilter(types=frozenset({"approval_asked", "approval_answered", "approval_closed"}))


async def test_it_is_lattice_cores_approvals_store(storage: Storage) -> None:
    assert isinstance(_store(await _grants(storage), Clock()), Approvals)


async def test_an_approval_asked_is_pending_in_its_tenant_and_audited(storage: Storage) -> None:
    grants = await _grants(storage)
    approvals = _store(grants, Clock())
    asked = await approvals.ask(_request())
    assert (asked.state, asked.asked_at, asked.answer) == ("pending", NOW, None)
    assert asked.id.startswith("apr~acme~")
    assert await approvals.get(asked.id) == asked
    [entry] = await grants.audit("acme", by=ALICE, keep=APPROVALS)
    assert entry.by == CAROL, "made for the person the run acts for"
    assert entry.event == ApprovalAsked(
        approval=asked.id, workspace="w1", capability="artifactr.edit_text", caller="run:run_1"
    )
    alone = RunCaller(id="run_2", agent="nightly")
    await approvals.ask(_request(asked_by=alone))
    entries = await grants.audit("acme", by=ALICE, keep=APPROVALS)
    assert entries[-1].by is None, "a run that acts for no one"


async def test_an_approval_is_asked_only_in_a_tenant(storage: Storage) -> None:
    approvals = _store(await _grants(storage), Clock())
    with pytest.raises(Invalid, match="there is no tenant initech"):
        await approvals.ask(_request(tenant="initech"))
    with pytest.raises(Invalid, match="has no ~"):
        await approvals.ask(_request(tenant="~deployment"))


async def test_an_answer_settles_it_and_is_audited(storage: Storage) -> None:
    grants = await _grants(storage)
    clock = Clock()
    approvals = _store(grants, clock)
    asked = await approvals.ask(_request())
    clock.now = NOW + timedelta(minutes=5)
    answered = await approvals.answer(asked.id, _answer(), subject=_as(BOB))
    assert answered.state == "approved"
    assert answered.answer is not None
    assert (answered.answer.by, answered.answer.at) == (_as(BOB), clock.now)
    assert await approvals.get(asked.id) == answered
    entry = (await grants.audit("acme", by=ALICE, keep=APPROVALS))[-1]
    assert entry.by == BOB
    assert entry.event == ApprovalAnswered(approval=asked.id, approved=True, surface="portalr")
    denied = await approvals.ask(_request())
    no = await approvals.answer(denied.id, _answer(approved=False), subject=_as(ALICE))
    assert no.state == "denied", "the tenant's owner holds the action too"


async def test_a_second_answer_is_refused_with_the_first(storage: Storage) -> None:
    approvals = _store(await _grants(storage), Clock())
    asked = await approvals.ask(_request())
    first = await approvals.answer(asked.id, _answer(), subject=_as(BOB))
    with pytest.raises(AlreadyAnswered) as refused:
        await approvals.answer(asked.id, _answer(approved=False), subject=_as(ALICE))
    assert refused.value.first == first.answer
    assert refused.value.approval == first


async def test_the_first_of_many_answers_at_once_wins(storage: Storage) -> None:
    """RFC-0011's race test: answers from many tasks at once, and exactly one wins."""
    grants = await _grants(storage)
    approvals = _store(grants, Clock())
    asked = await approvals.ask(_request())
    answers = [
        approvals.answer(
            asked.id, _answer(approved=i % 2 == 0), subject=_as(ALICE if i % 2 else BOB)
        )
        for i in range(20)
    ]
    results = await asyncio.wait_for(asyncio.gather(*answers, return_exceptions=True), 60)
    won = [result for result in results if isinstance(result, Approval)]
    lost = [result for result in results if isinstance(result, AlreadyAnswered)]
    assert (len(won), len(lost)) == (1, 19)
    assert all(refusal.first == won[0].answer for refusal in lost)
    assert await approvals.get(asked.id) == won[0]
    answered = await grants.audit(
        "acme", by=ALICE, keep=AuditFilter(types=frozenset({"approval_answered"}))
    )
    assert len(answered) == 1, "one answer, audited once"


async def test_an_answer_to_other_arguments_or_with_a_scope_is_refused(
    storage: Storage,
) -> None:
    approvals = _store(await _grants(storage), Clock())
    asked = await approvals.ask(_request())
    other = Answer(approved=True, arguments_digest="0" * 64, surface="portalr")
    with pytest.raises(DigestMismatch, match="other arguments"):
        await approvals.answer(asked.id, other, subject=_as(BOB))
    scoped = _answer().model_copy(
        update={"scope": AnswerScope(within="run", patterns=("edit_text",))}
    )
    with pytest.raises(ScopeNotOffered, match="no scoped answer"):
        await approvals.answer(asked.id, scoped, subject=_as(BOB))
    assert (await approvals.get(asked.id)).state == "pending", "neither counted"


async def test_who_holds_the_action_on_its_workspace_may_answer(storage: Storage) -> None:
    approvals = _store(await _grants(storage), Clock())
    asked = await approvals.ask(_request())
    elsewhere = await approvals.ask(_request(workspace="w2"))
    assert await approvals.may_answer(asked, _as(BOB))
    assert not await approvals.may_answer(elsewhere, _as(BOB)), "w1's admin, not w2's"
    assert await approvals.may_answer(elsewhere, _as(ALICE)), "the owner's, everywhere"
    with pytest.raises(NotAnAnswerer, match="carol may not answer"):
        await approvals.answer(asked.id, _answer(), subject=_as(CAROL))
    assert not await approvals.may_answer(asked, _as(DAVE)), "another tenant's owner"


async def test_a_named_subject_or_group_may_answer_by_grantrs_groups(storage: Storage) -> None:
    approvals = _store(await _grants(storage), Clock())
    named = await approvals.ask(_request(Answerers(subjects=frozenset({ERIN.id}))))
    grouped = await approvals.ask(_request(Answerers(groups=frozenset({APPROVERS.id}))))
    nobody = await approvals.ask(_request(Answerers(groups=frozenset({"nobody"}))))
    assert await approvals.may_answer(named, _as(ERIN))
    assert not await approvals.may_answer(named, _as(BOB)), "the action isn't named"
    assert await approvals.may_answer(grouped, _as(ERIN))
    claimed = _as(CAROL, groups=frozenset({APPROVERS.id}))
    assert not await approvals.may_answer(grouped, claimed), "a group claimed counts for nothing"
    assert not await approvals.may_answer(nobody, _as(ERIN))
    outsider = await approvals.ask(_request(Answerers(subjects=frozenset({DAVE.id}))))
    assert not await approvals.may_answer(outsider, _as(DAVE)), "named, but no member"


async def test_a_different_approver_is_never_the_person_who_asked(storage: Storage) -> None:
    approvals = _store(await _grants(storage), Clock())
    both = Answerers(subjects=frozenset({CAROL.id, BOB.id}), different_approver=True)
    asked = await approvals.ask(_request(both))
    with pytest.raises(NotAnAnswerer):
        await approvals.answer(asked.id, _answer(), subject=_as(CAROL))
    assert (await approvals.answer(asked.id, _answer(), subject=_as(BOB))).state == "approved"
    alone = await approvals.ask(
        _request(
            Answerers(action="grantr:answer_approval", different_approver=True),
            asked_by=PersonCaller(id=BOB.id),
        )
    )
    assert not await approvals.may_answer(alone, _as(BOB)), "holding the action is no exception"
    assert await approvals.may_answer(alone, _as(ALICE))


async def test_a_confirmation_is_its_callers_alone_on_the_confirm_page(storage: Storage) -> None:
    approvals = _store(await _grants(storage), Clock())
    confirm = Answerers(subjects=frozenset({CAROL.id}), confirmation=True)
    asked = await approvals.ask(_request(confirm, asked_by=PersonCaller(id=CAROL.id)))
    assert not await approvals.may_answer(asked, _as(ALICE)), "not even the owner"
    assert not await approvals.may_answer(asked, Subject(id=CAROL.id, service=True))
    with pytest.raises(NotAnAnswerer, match=f"confirmed on {CONFIRM_SURFACE} alone"):
        await approvals.answer(asked.id, _answer(surface="mcp"), subject=_as(CAROL))
    confirmed = await approvals.answer(
        asked.id, _answer(surface=CONFIRM_SURFACE), subject=_as(CAROL)
    )
    assert confirmed.state == "approved"


async def test_a_service_principal_answers_only_by_a_grant_made_to_it(
    storage: Storage,
) -> None:
    grants = await _grants(storage)
    approvals = _store(grants, Clock())
    named = await approvals.ask(_request(Answerers(subjects=frozenset({BOT.id}))))
    grouped = await approvals.ask(_request(Answerers(groups=frozenset({APPROVERS.id}))))
    by_action = await approvals.ask(_request())
    assert not await approvals.may_answer(named, _as(BOT)), "subjects name people"
    assert not await approvals.may_answer(grouped, _as(BOT)), "never by a group it is in"
    approver = Role(name="approver", actions=frozenset({"grantr:answer_approval"}))
    await grants.define_role("acme", approver, by=ALICE)
    await grants.grant("acme", "approver", on=W1, to=APPROVERS, by=ALICE)
    assert await approvals.may_answer(by_action, _as(ERIN)), "a person holds it by a group"
    assert not await approvals.may_answer(by_action, _as(BOT)), "a principal doesn't"
    await grants.grant("acme", "approver", on=W1, to=BOT, by=ALICE)
    assert await approvals.may_answer(by_action, _as(BOT)), "a grant made to it, a custom role"
    approved = await approvals.answer(by_action.id, _answer(), subject=_as(BOT))
    assert approved.answer is not None
    assert approved.answer.by == _as(BOT)
    entry = (await grants.audit("acme", by=ALICE, keep=APPROVALS))[-1]
    assert entry.by == BOT


async def test_a_principal_with_a_persons_id_cant_answer_as_them(storage: Storage) -> None:
    grants = await _grants(storage)
    approvals = _store(grants, Clock())
    twin = ServicePrincipal(id=ERIN.id)
    await grants.add_member("acme", twin, by=ALICE)
    erins = await approvals.ask(_request(Answerers(subjects=frozenset({ERIN.id}))))
    assert await approvals.may_answer(erins, _as(ERIN))
    with pytest.raises(NotAnAnswerer):
        await approvals.answer(erins.id, _answer(), subject=_as(twin))


async def test_a_member_removed_answers_nothing(storage: Storage) -> None:
    grants = await _grants(storage)
    approvals = _store(grants, Clock())
    asked = await approvals.ask(_request(Answerers(subjects=frozenset({ERIN.id}))))
    await grants.remove_member("acme", ERIN, by=ALICE)
    assert not await approvals.may_answer(asked, _as(ERIN))


async def test_an_approval_past_its_deadline_takes_no_answer(storage: Storage) -> None:
    clock = Clock()
    approvals = _store(await _grants(storage), clock)
    asked = await approvals.ask(_request())
    clock.now = asked.deadline
    with pytest.raises(NotPending, match="past its deadline"):
        await approvals.answer(asked.id, _answer(), subject=_as(BOB))
    assert (await approvals.get(asked.id)).state == "pending", "the sweep closes it"


async def test_an_approved_approval_is_taken_once(storage: Storage) -> None:
    clock = Clock()
    approvals = _store(await _grants(storage), clock)
    asked = await approvals.ask(_request())
    with pytest.raises(NotApproved, match="is pending"):
        await approvals.take(asked.id)
    await approvals.answer(asked.id, _answer(), subject=_as(BOB))
    clock.now = NOW + timedelta(minutes=1)
    takes = await asyncio.gather(
        *(approvals.take(asked.id) for _ in range(10)), return_exceptions=True
    )
    taken = [result for result in takes if isinstance(result, Approval)]
    assert len(taken) == 1
    assert sum(isinstance(result, NotApproved) for result in takes) == 9
    assert taken[0].taken_at == clock.now
    with pytest.raises(NotApproved, match="let its one call through"):
        await approvals.take(asked.id)
    denied = await approvals.ask(_request())
    await approvals.answer(denied.id, _answer(approved=False), subject=_as(BOB))
    with pytest.raises(NotApproved, match="is denied"):
        await approvals.take(denied.id)


async def test_a_withdrawn_approval_takes_no_answer(storage: Storage) -> None:
    grants = await _grants(storage)
    approvals = _store(grants, Clock())
    asked = await approvals.ask(_request())
    withdrawn = await approvals.withdraw(asked.id, "the run stopped")
    assert (withdrawn.state, withdrawn.reason) == ("withdrawn", "the run stopped")
    entry = (await grants.audit("acme", by=ALICE, keep=APPROVALS))[-1]
    assert entry.by is None
    assert entry.event == ApprovalClosed(
        approval=asked.id, state="withdrawn", reason="the run stopped"
    )
    with pytest.raises(NotPending, match="is withdrawn"):
        await approvals.answer(asked.id, _answer(), subject=_as(BOB))
    with pytest.raises(NotPending):
        await approvals.withdraw(asked.id, "again")


async def test_the_sweep_expires_what_is_due_in_every_tenant(storage: Storage) -> None:
    grants = await _grants(storage)
    clock = Clock()
    approvals = _store(grants, clock)
    soon = NOW + timedelta(minutes=10)
    due = await approvals.ask(_request(deadline=soon))
    later = await approvals.ask(_request())
    elsewhere = await approvals.ask(_request(tenant="globex", deadline=soon))
    answered = await approvals.ask(_request(deadline=soon))
    await approvals.answer(answered.id, _answer(), subject=_as(BOB))
    assert await approvals.expire_due() == [], "nothing due yet"
    clock.now = soon
    expired = await approvals.expire_due()
    assert [a.id for a in expired] == [due.id, elsewhere.id]
    assert {(a.state, a.reason) for a in expired} == {("expired", EXPIRED)}
    assert (await approvals.get(later.id)).state == "pending"
    assert (await approvals.get(answered.id)).state == "approved"
    entry = (await grants.audit("globex", by=DAVE, keep=APPROVALS))[-1]
    assert entry.event == ApprovalClosed(approval=elsewhere.id, state="expired", reason=EXPIRED)
    with pytest.raises(NotPending, match="is expired"):
        await approvals.answer(due.id, _answer(), subject=_as(BOB))
    assert await approvals.expire_due() == [], "each once"


async def test_pending_lists_what_the_subject_may_answer_in_the_scope(storage: Storage) -> None:
    clock = Clock()
    approvals = _store(await _grants(storage), clock)
    first = await approvals.ask(_request())
    clock.now = NOW + timedelta(minutes=1)
    erins = await approvals.ask(_request(Answerers(subjects=frozenset({ERIN.id}))))
    second = await approvals.ask(_request())
    await approvals.ask(_request(workspace="w2"))
    settled = await approvals.ask(_request())
    await approvals.withdraw(settled.id, "the run stopped")
    w1 = Scope(tenant_id="acme", workspace_id="w1")
    assert await approvals.pending(w1, _as(BOB)) == [first, second], "oldest first"
    assert await approvals.pending(w1, _as(ERIN)) == [erins]
    assert await approvals.pending(Scope(tenant_id="globex", workspace_id="w1"), _as(BOB)) == []
    deployment = Scope(tenant_id="~deployment", workspace_id="w1")
    assert await approvals.pending(deployment, _as(BOB)) == []


@pytest.mark.parametrize(
    "id",
    ["apr_1", "apr~acme", "apr~acme~", "apr~~token", "xyz~acme~token", "apr~acme~a~b"],
)
async def test_an_id_that_isnt_an_approvals_is_unknown(storage: Storage, id: str) -> None:
    approvals = _store(await _grants(storage), Clock())
    with pytest.raises(UnknownApproval, match=f"no approval {id}"):
        await approvals.get(id)
    with pytest.raises(UnknownApproval):
        await approvals.answer(id, _answer(), subject=_as(BOB))


async def test_an_approval_is_its_tenants_alone(storage: Storage) -> None:
    grants = await _grants(storage)
    approvals = _store(grants, Clock())
    asked = await approvals.ask(_request())
    elsewhere = asked.id.replace("apr~acme~", "apr~globex~")
    for each in (approvals.get, approvals.take):
        with pytest.raises(UnknownApproval):
            await each(elsewhere)
    with pytest.raises(UnknownApproval):
        await approvals.withdraw(elsewhere, "no")
    assert await storage.approval("globex", asked.id) is None
    assert await storage.approvals("globex") == []
    gone = await approvals.ask(_request(tenant="globex"))
    await grants.delete_tenant("globex", by=DAVE)
    with pytest.raises(UnknownApproval):
        await approvals.get(gone.id)
    assert (await approvals.get(asked.id)).state == "pending", "acme's stays"


async def test_watch_yields_each_change_until_it_is_settled(storage: Storage) -> None:
    approvals = _store(await _grants(storage), Clock())
    asked = await approvals.ask(_request())
    watching = approvals.watch(asked.id)
    assert await anext(watching) == asked
    following = asyncio.ensure_future(anext(watching))
    await asyncio.sleep(0.05)
    assert not following.done(), "nothing has changed"
    answered = await approvals.answer(asked.id, _answer(), subject=_as(BOB))
    assert await asyncio.wait_for(following, 10) == answered
    with pytest.raises(StopAsyncIteration):
        await anext(watching)
    with pytest.raises(UnknownApproval):
        await anext(approvals.watch("apr~acme~missing"))


async def test_the_default_clock_is_the_systems() -> None:
    approvals = (await _grants(InMemoryStorage())).approvals()
    before = datetime.now(NOW.tzinfo)
    asked = await approvals.ask(_request(deadline=before + timedelta(hours=1)))
    assert before <= asked.asked_at <= datetime.now(NOW.tzinfo)
