"""grantr's answers to lattice-core's enforcer over every storage (grantr ADR-0039).

``Authorize`` checks a call's caller as the person it is or acts for, in the call's workspace;
``Audit`` records every call in its tenant's log, or the deployment's for a tenant that doesn't
exist.
"""

from datetime import UTC, datetime
from typing import Any

import pytest

from grantr.core import (
    Agent,
    AuditFilter,
    CapabilityCalled,
    CapabilityStep,
    Resource,
    Subject,
    User,
)
from grantr.grants import Grants, Storage
from grantr.grants.calls import subject_of_call
from lattice_core.capabilities import (
    CallContext,
    Caller,
    PersonCaller,
    RunCaller,
    Scope,
    SessionCaller,
    Via,
)
from lattice_core.enforcement import Audit, Step
from lattice_core.enforcement import CapabilityCalled as Called
from lattice_core.taint import Clean
from tests.catalogs import ARTIFACTR, PORTALR, REFLEXR
from tests.grants.conftest import ALICE, ROOT

CAROL = User(id="carol")
"""acme's w1's editor."""

W1 = Resource(kind="workspace", workspace="w1")
EDIT = "artifactr:edit_artifact"
CALLS = AuditFilter(types=frozenset({"capability_called"}))
CLIENT = Via(connection_id="conn_1", client_name="Claude", surface="mcp")
AT = datetime(2026, 11, 1, 1, tzinfo=UTC)


async def _grants(storage: Storage) -> Grants:
    grants = Grants(storage, catalogs=[ARTIFACTR, REFLEXR, PORTALR])
    await grants.first_operator(ROOT.id)
    await grants.create_tenant("acme", owner=ALICE.id, by=ROOT)
    await grants.add_member("acme", CAROL, by=ALICE)
    await grants.grant("acme", "editor", on=W1, to=CAROL, by=ALICE)
    return grants


def _context(
    caller: Caller, *, tenant: str = "acme", workspace: str = "w1", via: Via | None = None
) -> CallContext:
    return CallContext(
        scope=Scope(tenant_id=tenant, workspace_id=workspace),
        caller=caller,
        taint=Clean(),
        correlation_id="turn_1",
        surface="portalr",
        via=via,
    )


@pytest.mark.parametrize(
    ("caller", "subject"),
    [
        (PersonCaller(id="carol"), User(id="carol")),
        (RunCaller(id="run_1", agent="helper", on_behalf_of="carol"), User(id="carol")),
        (SessionCaller(id="ses_1", on_behalf_of="carol"), User(id="carol")),
        (RunCaller(id="run_2", agent="nightly"), Agent()),
        (SessionCaller(id="ses_2"), Agent()),
    ],
)
def test_a_call_is_checked_as_the_person_it_is_for_or_the_agent(
    caller: Caller, subject: Subject
) -> None:
    assert subject_of_call(_context(caller)) == subject


async def test_authorize_checks_the_gate_in_the_calls_workspace(storage: Storage) -> None:
    authorize = (await _grants(storage)).authorize()
    run = RunCaller(id="run_1", agent="helper", on_behalf_of="carol")
    assert await authorize(_context(PersonCaller(id="carol")), EDIT)
    assert await authorize(_context(run), EDIT), "the run holds what its person holds"
    assert await authorize(_context(PersonCaller(id="carol"), via=CLIENT), EDIT), "a client"
    assert not await authorize(_context(run, workspace="w2"), EDIT), "only where it is held"
    assert not await authorize(_context(RunCaller(id="run_2", agent="nightly")), EDIT)
    assert not await authorize(_context(PersonCaller(id="dave")), EDIT), "no member"
    assert not await authorize(_context(PersonCaller(id="carol")), "artifactr:nope")


async def test_a_call_naming_no_tenant_holds_nothing(storage: Storage) -> None:
    grants = await _grants(storage)
    authorize = grants.authorize()
    assert not await authorize(_context(PersonCaller(id="root"), tenant="~deployment"), EDIT)
    assert not await authorize(_context(PersonCaller(id="carol"), tenant="globex"), EDIT)
    everyone = grants.authorize(subject_of=lambda _context: ALICE)
    assert await everyone(_context(PersonCaller(id="carol"), workspace="w2"), EDIT), "the owner"


def _called(**changes: Any) -> Called:
    fields: dict[str, Any] = {
        "capability": "artifactr.edit_text",
        "version": "1.0.0",
        "scope": Scope(tenant_id="acme", workspace_id="w1"),
        "caller": "run:run_1",
        "on_behalf_of": "carol",
        "via": None,
        "correlation_id": "run_1",
        "surface": "portalr",
        "arguments_digest": "a" * 64,
        "steps": (
            Step(name="integration", passed=True),
            Step(name="grant", passed=True),
            Step(name="approval", passed=False, note="apr~acme~1"),
        ),
        "outcome": "pending",
        "approval": "apr~acme~1",
        "at": AT,
    }
    return Called.model_validate(fields | changes)


async def test_every_call_is_audited_in_its_tenant(storage: Storage) -> None:
    grants = await _grants(storage)
    audit = grants.capability_audit()
    assert isinstance(audit, Audit)
    await audit.record(_called())
    [entry] = await grants.audit("acme", by=ALICE, keep=CALLS)
    assert entry.by == CAROL, "made by the person it was for"
    assert entry.event == CapabilityCalled(
        capability="artifactr.edit_text",
        version="1.0.0",
        workspace="w1",
        caller="run:run_1",
        correlation_id="run_1",
        surface="portalr",
        arguments_digest="a" * 64,
        steps=(
            CapabilityStep(name="integration", passed=True),
            CapabilityStep(name="grant", passed=True),
            CapabilityStep(name="approval", passed=False, note="apr~acme~1"),
        ),
        outcome="pending",
        approval="apr~acme~1",
        called_at=AT,
    )
    await audit.record(
        _called(on_behalf_of=None, via=CLIENT, outcome="refused", version=None, approval=None)
    )
    entry = (await grants.audit("acme", by=ALICE, keep=CALLS))[-1]
    assert entry.by == Agent(), "an agent acting for no one"
    assert isinstance(entry.event, CapabilityCalled)
    assert (entry.event.client, entry.event.outcome) == ("Claude (conn_1)", "refused")


async def test_a_call_naming_a_tenant_that_doesnt_exist_is_the_deployments(
    storage: Storage,
) -> None:
    grants = await _grants(storage)
    audit = grants.capability_audit()
    for tenant in ("globex", "~forged"):
        await audit.record(_called(scope=Scope(tenant_id=tenant, workspace_id="w1")))
    entries = await grants.audit(None, by=ROOT, keep=CALLS)
    assert [e.event.tenant for e in entries if isinstance(e.event, CapabilityCalled)] == [
        "globex",
        "~forged",
    ], "the operators see a forged scope"
    assert await grants.audit("acme", by=ALICE, keep=CALLS) == []
