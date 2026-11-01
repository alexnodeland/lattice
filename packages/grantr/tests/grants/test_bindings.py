"""grantr's bindings over every storage (lattice ADR-0040, grantr ADR-0041).

A tenant's owners and admins bind its sources to its workspaces, each change audited; the
operator's bindings are read only; the intake reads a connection's bindings in every tenant, and
a binding is its tenant's alone.
"""

from datetime import UTC, datetime
from typing import Any

import pytest

from grantr.core import (
    TENANT,
    Agent,
    AuditFilter,
    BindingAdded,
    BindingRemoved,
    Forbidden,
    Invalid,
    Resource,
    RulePrincipal,
    ServicePrincipal,
    User,
)
from grantr.grants import Grants, Storage
from lattice_core.bindings import Binding, Bindings
from tests.catalogs import ARTIFACTR, PORTALR, REFLEXR
from tests.grants.conftest import ALICE, NOW, ROOT

BOB = User(id="bob")
"""acme's admin."""

CAROL = User(id="carol")
"""w1's admin, who holds nothing on the tenant."""

DAVE = User(id="dave")
"""globex's owner."""

CI = ServicePrincipal(id="ci")
"""acme's service principal, granted admin on the tenant."""

BINDINGS = AuditFilter(types=frozenset({"binding_added", "binding_removed"}))


def _operators(**changes: Any) -> Binding:
    fields: dict[str, Any] = {
        "id": "bnd_" + "0" * 16,
        "tenant_id": "acme",
        "workspace_id": "w1",
        "source": "tracker",
        "connection": "plane",
        "select": {"project": "OPS"},
        "bound_at": datetime(2026, 10, 1, tzinfo=UTC),
        "by": "operator",
    }
    return Binding.model_validate(fields | changes)


async def _grants(storage: Storage, *operator: Binding) -> Grants:
    grants = Grants(storage, catalogs=[ARTIFACTR, REFLEXR, PORTALR], operator_bindings=operator)
    await grants.first_operator(ROOT.id)
    await grants.create_tenant("acme", owner=ALICE.id, by=ROOT)
    for member in (BOB, CAROL, CI):
        await grants.add_member("acme", member, by=ALICE)
    await grants.grant("acme", "admin", on=TENANT, to=BOB, by=ALICE)
    await grants.grant("acme", "admin", on=TENANT, to=CI, by=ALICE)
    w1 = Resource(kind="workspace", workspace="w1")
    await grants.grant("acme", "admin", on=w1, to=CAROL, by=ALICE)
    await grants.create_tenant("globex", owner=DAVE.id, by=ROOT)
    return grants


async def test_an_owner_binds_a_source_and_it_is_audited(storage: Storage) -> None:
    grants = await _grants(storage)
    entry = await grants.bindings().bind(
        "acme",
        "w1",
        "forge",
        "inst_1",
        select={"repository": "acme/api"},
        types=["forge:pull_request", "forge:issue"],
        trust="untrusted",
        options={"labels": ["triage"]},
        by=ALICE,
    )
    assert isinstance(entry.event, BindingAdded)
    assert (entry.by, entry.tenant) == (ALICE, "acme")
    assert entry.event.types == ["forge:issue", "forge:pull_request"], "sorted"
    [bound] = await grants.bindings().listed("acme", by=ALICE)
    assert bound.id == entry.event.binding
    assert (bound.workspace_id, bound.source, bound.connection) == ("w1", "forge", "inst_1")
    assert (bound.select, bound.trust, bound.options) == (
        {"repository": "acme/api"},
        "untrusted",
        {"labels": ["triage"]},
    )
    assert (bound.bound_at, bound.by) == (NOW, "user:alice")
    [audited] = await grants.audit("acme", by=ALICE, keep=BINDINGS)
    assert audited == entry


async def test_a_tenants_admins_bind_and_no_one_else(storage: Storage) -> None:
    grants = await _grants(storage)
    bindings = grants.bindings()
    await bindings.bind("acme", "w1", "forge", "inst_1", by=BOB)
    await bindings.bind("acme", "w1", "forge", "inst_2", by=CI)
    stored = await bindings.listed("acme", by=BOB)
    assert sorted(b.by for b in stored) == ["service_principal:ci", "user:bob"]
    refused = (CAROL, DAVE, Agent(), RulePrincipal(workspace="w1", rule="r"))
    for who in refused:
        with pytest.raises(Forbidden, match="grantr:manage_bindings on the tenant"):
            await bindings.bind("acme", "w1", "forge", "inst_3", by=who)
    with pytest.raises(Forbidden):
        await bindings.listed("acme", by=CAROL)


@pytest.mark.parametrize(
    ("changes", "says"),
    [
        ({"source": "Forge"}, "a source's name is lowercase"),
        ({"workspace": ""}, "names a workspace and a connection"),
        ({"connection": ""}, "names a workspace and a connection"),
        ({"types": []}, "receives some types"),
    ],
)
async def test_a_binding_not_well_formed_is_invalid(
    storage: Storage, changes: dict[str, Any], says: str
) -> None:
    grants = await _grants(storage)
    given: dict[str, Any] = {"workspace": "w1", "source": "forge", "connection": "inst_1"}
    asked = given | changes
    with pytest.raises(Invalid, match=says):
        await grants.bindings().bind(
            "acme",
            asked.pop("workspace"),
            asked.pop("source"),
            asked.pop("connection"),
            by=ALICE,
            **asked,
        )
    assert await grants.audit("acme", by=ALICE, keep=BINDINGS) == []


async def test_unbinding_removes_it_and_is_audited(storage: Storage) -> None:
    grants = await _grants(storage)
    bindings = grants.bindings()
    added = await bindings.bind("acme", "w1", "forge", "inst_1", by=ALICE)
    assert isinstance(added.event, BindingAdded)
    id = added.event.binding
    removed = await bindings.unbind("acme", id, by=BOB)
    assert removed.event == BindingRemoved(
        binding=id, workspace="w1", source="forge", connection="inst_1"
    )
    assert await bindings.listed("acme", by=ALICE) == []
    with pytest.raises(Invalid, match=f"there is no binding {id}"):
        await bindings.unbind("acme", id, by=ALICE)
    with pytest.raises(Forbidden):
        await bindings.unbind("acme", id, by=CAROL)


async def test_a_binding_is_its_tenants_alone(storage: Storage) -> None:
    grants = await _grants(storage)
    bindings = grants.bindings()
    added = await bindings.bind("acme", "w1", "forge", "inst_1", by=ALICE)
    assert isinstance(added.event, BindingAdded)
    with pytest.raises(Invalid, match="there is no binding"):
        await bindings.unbind("globex", added.event.binding, by=DAVE)
    assert await bindings.listed("globex", by=DAVE) == []
    assert await bindings.for_workspace("globex", "w1") == []
    await grants.delete_tenant("acme", by=ALICE)
    assert await bindings.for_connection("forge", "inst_1") == [], "deleted with its tenant"


async def test_the_operators_bindings_come_first_and_are_read_only(storage: Storage) -> None:
    operators = _operators()
    grants = await _grants(storage, operators, _operators(id="bnd_" + "1" * 16, tenant_id="globex"))
    bindings = grants.bindings()
    await bindings.bind("acme", "w1", "tracker", "plane", select={"project": "API"}, by=ALICE)
    await bindings.bind("acme", "w2", "forge", "inst_1", by=ALICE)
    listed = await bindings.listed("acme", by=ALICE)
    assert listed[0] == operators, "the operator's first"
    assert sorted(b.workspace_id for b in listed[1:]) == ["w1", "w2"]
    assert [b.source for b in await bindings.listed("acme", by=ALICE, workspace="w2")] == ["forge"]
    with pytest.raises(Invalid, match="the operator's, set in the deployment's configuration"):
        await bindings.unbind("acme", operators.id, by=ALICE)


async def test_the_intake_reads_a_connections_bindings_in_every_tenant(storage: Storage) -> None:
    operators = _operators()
    grants = await _grants(storage, operators)
    bindings = grants.bindings()
    assert isinstance(bindings, Bindings)
    await bindings.bind("acme", "w2", "tracker", "plane", by=ALICE)
    await bindings.bind("globex", "ops", "tracker", "plane", by=DAVE)
    await bindings.bind("globex", "ops", "tracker", "vikunja", by=DAVE)
    found = await bindings.for_connection("tracker", "plane")
    assert found[0] == operators, "the operator's first"
    assert sorted((b.tenant_id, b.workspace_id) for b in found[1:]) == [
        ("acme", "w2"),
        ("globex", "ops"),
    ], "then each tenant's"
    assert [b.workspace_id for b in await bindings.for_workspace("acme", "w1")] == ["w1"]
    assert len(await bindings.for_workspace("globex", "ops")) == 2
    assert await bindings.for_workspace("~deployment", "w1") == []


def test_the_operator_binds_an_id_once(storage: Storage) -> None:
    with pytest.raises(ValueError, match="the operator binds bnd_0000000000000000 twice"):
        Grants(storage, operator_bindings=[_operators(), _operators(workspace_id="w2")])


async def test_a_binding_names_a_tenant_one_can_have(storage: Storage) -> None:
    grants = await _grants(storage)
    with pytest.raises(Invalid, match="a tenant's id isn't empty, and has no ~"):
        await grants.bindings().bind("~deployment", "w1", "forge", "inst_1", by=ROOT)
