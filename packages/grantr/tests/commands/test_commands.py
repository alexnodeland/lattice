"""grantr's commands (lattice RFC-0014, grantr ADR-0042): a static catalog of every action on
access, and its provider, which runs each as the subject a call is for, through the enforcer."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from grantr.commands import ADMIN_HIGH, CATALOG, GrantrProvider, provider
from grantr.core import GRANTR_ACTIONS, ClientInfo, ServicePrincipal, User
from grantr.core import Forbidden as Refused
from grantr.grants import Grants, InMemoryStorage
from lattice_core.approvals import (
    Answerers,
    ApprovalRequest,
    NoCoverage,
    Rendering,
    SettingsPolicy,
    admin_high_approvers,
    arguments_digest,
)
from lattice_core.capabilities import (
    CallContext,
    Caller,
    PersonCaller,
    Registry,
    RunCaller,
    Scope,
)
from lattice_core.commands import Command, NotExposed, catalog
from lattice_core.enforcement import (
    ApprovalPending,
    Enforcer,
    FakeCounter,
    FixedCeilings,
    FixedTaint,
    Forbidden,
)
from lattice_core.settings import KNOWN_SETTINGS, registry
from lattice_core.taint import Clean
from tests.catalogs import ARTIFACTR

ROOT = User(id="root")
ALICE = User(id="alice")
COMMANDS = {command.name: command for command in CATALOG.commands()}


def _context(caller: Caller | None = None, *, tenant: str = "acme") -> CallContext:
    return CallContext(
        scope=Scope(tenant_id=tenant, workspace_id="w1"),
        caller=caller or PersonCaller(id="alice"),
        taint=Clean(),
        correlation_id="turn_1",
        surface="mcp",
    )


async def _grants() -> Grants:
    grants = Grants(InMemoryStorage(), catalogs=[ARTIFACTR])
    await grants.first_operator(ROOT.id)
    await grants.create_tenant("acme", owner=ALICE.id, by=ROOT)
    return grants


async def _call(
    bound: GrantrProvider, command: str, context: CallContext | None = None, /, **arguments: Any
) -> Any:
    answer = await bound.call(COMMANDS[command].capability, arguments, context or _context())
    return _parsed(answer.output)


def _parsed(output: object) -> Any:
    assert isinstance(output, str), "every command answers JSON text"
    return json.loads(output)


def test_every_command_is_grantrs_and_gated_by_a_grantr_action() -> None:
    for command in COMMANDS.values():
        assert isinstance(command, Command)
        assert command.name.startswith("grantr.")
        assert command.capability.gate.action in GRANTR_ACTIONS
    assert list(catalog(CATALOG)) == list(COMMANDS), "no two share a name or a tool name"


def test_every_grantr_action_is_some_commands_gate() -> None:
    gates = {command.capability.gate.action for command in COMMANDS.values()}
    # Creating a tenant is portalr's command, which asks for its name and owner (RFC-0014).
    assert gates == GRANTR_ACTIONS - {"grantr:create_tenant"}


def test_the_high_risk_ones_are_admin_high_and_answering_and_issuing_keys_are_no_tools() -> None:
    expected = {
        "grantr.define_role",
        "grantr.grant_on_tenant",
        "grantr.revoke_key",
        "grantr.delete_tenant",
        "grantr.grant_operator",
        "grantr.revoke_member_connection",
    }
    assert expected == ADMIN_HIGH
    assert {n for n, c in COMMANDS.items() if c.capability.risk_class == "admin_high"} == ADMIN_HIGH
    hidden = {n for n, c in COMMANDS.items() if isinstance(c.exposure, NotExposed)}
    assert hidden == {"grantr.answer_approval", "grantr.issue_key"}
    assert all(COMMANDS[n].surfaces == {"portalr"} for n in hidden)
    assert {n for n, c in COMMANDS.items() if c.toolset == "core"} == {
        "grantr.list_approvals",
        "grantr.read_approval",
        "grantr.answer_approval",
    }


async def test_the_provider_offers_what_a_client_may_call() -> None:
    bound = provider(await _grants())
    offered = {c.name for c in bound.capabilities(Scope(tenant_id="acme", workspace_id="w1"))}
    assert offered == set(COMMANDS) - {"grantr.answer_approval", "grantr.issue_key"}
    assert bound.kind == "command"


async def test_members_groups_roles_and_grants_run_as_the_caller() -> None:
    grants = await _grants()
    bound = provider(grants)
    bob = {"kind": "user", "id": "bob"}
    added = await _call(bound, "grantr.add_member", member=bob)
    assert (added["event"]["type"], added["by"]) == (
        "member_added",
        {"kind": "user", "id": "alice"},
    )
    assert bob in await _call(bound, "grantr.list_members")
    await _call(bound, "grantr.define_group", group="team", members=[bob])
    assert await _call(bound, "grantr.list_groups") == {"team": [bob]}
    await _call(bound, "grantr.define_role", name="triage", actions=["artifactr:open"])
    assert await _call(bound, "grantr.list_roles") == [
        {"name": "triage", "actions": ["artifactr:open"]}
    ]
    on = {"kind": "workspace", "workspace": "w1"}
    await _call(bound, "grantr.grant", role="editor", on=on, to=bob)
    await _call(bound, "grantr.grant_on_tenant", role="admin", to=bob)
    listed = await _call(bound, "grantr.list_grants", workspace="w1")
    assert [g["role"] for g in listed] == ["editor"]
    await _call(bound, "grantr.revoke", role="editor", on=on, to=bob)
    await _call(bound, "grantr.delete_group", group="team")
    await _call(bound, "grantr.delete_role", name="triage")
    removed = await _call(bound, "grantr.remove_member", member=bob)
    assert removed["event"]["type"] == "member_removed"
    with pytest.raises(ValueError, match=r"granted by grantr\.grant_on_tenant"):
        await _call(bound, "grantr.grant", role="admin", on={"kind": "tenant"}, to=bob)


async def test_restrictions_keys_integrations_settings_and_the_audit_log() -> None:
    grants = await _grants()
    bound = provider(grants)
    ci = ServicePrincipal(id="ci")
    await grants.add_member("acme", ci, by=ALICE)
    _, issued = await grants.issue_key("acme", ci, by=ALICE)
    thread = {"kind": "thread", "workspace": "w1", "id": "t1"}
    restricted = await _call(bound, "grantr.restrict", on=thread)
    assert restricted["event"]["type"] == "restricted"
    assert await _call(bound, "grantr.list_restrictions", workspace="w1") == [thread]
    [key] = await _call(bound, "grantr.list_keys")
    revoked = await _call(bound, "grantr.revoke_key", key=key["id"])
    assert revoked["event"]["type"] == "key_revoked"
    states = await _call(bound, "grantr.list_integrations")
    key_name = states[0]["key"]
    switched = await _call(bound, "grantr.set_integration", key=key_name, on=True, workspace="w1")
    assert switched["key"] == key_name
    view = await _call(bound, "grantr.list_settings")
    setting = view["settings"][0]["key"]
    low = view["settings"][0]["kind"].get("low", 0)
    changed = await _call(bound, "grantr.set_setting", key=setting, value=low)
    assert changed["key"] == setting
    entries = await _call(bound, "grantr.read_audit", last=3, types=["key_revoked"])
    assert [e["event"]["type"] for e in entries] == ["key_revoked"]
    assert issued.event.type == "key_issued"


async def test_bindings_are_listed_bound_and_unbound_as_the_caller() -> None:
    grants = await _grants()
    bound = provider(grants)
    made = await _call(
        bound,
        "grantr.bind",
        workspace="w1",
        source="forge",
        connection="inst_1",
        types=["forge:issue"],
        trust="untrusted",
    )
    assert made["event"]["type"] == "binding_added"
    [binding] = await _call(bound, "grantr.list_bindings", workspace="w1")
    assert (binding["source"], binding["connection"], binding["trust"]) == (
        "forge",
        "inst_1",
        "untrusted",
    )
    gone = await _call(bound, "grantr.unbind", binding=binding["id"])
    assert gone["event"]["type"] == "binding_removed"
    assert await _call(bound, "grantr.list_bindings") == []


async def test_connections_are_listed_and_revoked_as_the_caller() -> None:
    grants = await _grants()
    bound = provider(grants)
    connections = grants.connections()
    bob = User(id="bob")
    await grants.add_member("acme", bob, by=ALICE)
    claude = ClientInfo(client_id="client_claude", name="Claude")
    alices = await connections.connect("acme", claude, by=ALICE)
    bobs = await connections.connect("acme", claude, by=bob)
    listed = await _call(bound, "grantr.list_connections")
    assert [c["id"] for c in listed] == [alices.id, bobs.id], "an owner reads every one"
    only = await _call(bound, "grantr.list_connections", user="bob")
    assert [c["id"] for c in only] == [bobs.id]
    with pytest.raises(Refused, match="isn't yours"):
        await _call(bound, "grantr.revoke_connection", connection=bobs.id)
    own = await _call(bound, "grantr.revoke_connection", connection=alices.id)
    assert own["event"]["type"] == "connection_revoked"
    theirs = await _call(bound, "grantr.revoke_member_connection", connection=bobs.id)
    assert theirs["event"]["user"] == "bob"


async def test_approvals_are_read_by_who_may_answer_them() -> None:
    grants = await _grants()
    bound = provider(grants)
    asked = await grants.approvals().ask(
        ApprovalRequest(
            scope=Scope(tenant_id="acme", workspace_id="w1"),
            capability="artifactr.edit_text",
            version="1.0.0",
            rendering=Rendering(title="Edit a1", arguments={"a": 1}),
            arguments_digest=arguments_digest({"a": 1}),
            asked_by=RunCaller(id="run_1", agent="helper", on_behalf_of="bob"),
            answerers=Answerers(action="grantr:answer_approval"),
            deadline=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    [listed] = await _call(bound, "grantr.list_approvals")
    assert listed["id"] == asked.id
    assert [a["id"] for a in await _call(bound, "grantr.list_approvals", workspace="w1")] == [
        asked.id
    ]
    read = await _call(bound, "grantr.read_approval", approval=asked.id)
    assert read["state"] == "pending"
    await grants.create_tenant("globex", owner=ALICE.id, by=ROOT)
    with pytest.raises(ValueError, match="no approval"):
        await _call(bound, "grantr.read_approval", _context(tenant="globex"), approval=asked.id)
    agent = _context(RunCaller(id="run_2", agent="nightly"))
    with pytest.raises(ValueError, match="only a member reads an approval"):
        await _call(bound, "grantr.list_approvals", agent)


async def test_the_tenant_and_the_operators() -> None:
    grants = await _grants()
    bound = provider(grants)
    root = _context(PersonCaller(id="root"))
    made = await _call(bound, "grantr.grant_operator", root, user="carol")
    assert made["event"]["type"] == "granted"
    taken = await _call(bound, "grantr.revoke_operator", root, user="carol")
    assert taken["event"]["type"] == "revoked"
    gone = await _call(bound, "grantr.delete_tenant")
    assert gone["event"]["type"] == "tenant_deleted"


async def test_what_isnt_offered_or_isnt_grantrs_is_refused() -> None:
    bound = provider(await _grants())
    with pytest.raises(ValueError, match="isn't called through the enforcer"):
        await _call(
            bound,
            "grantr.answer_approval",
            approval="apr~acme~x",
            approved=True,
            arguments_digest="a" * 64,
        )
    with pytest.raises(ValueError, match="isn't called through the enforcer"):
        await _call(bound, "grantr.issue_key", principal="ci")
    other = COMMANDS["grantr.list_members"].capability.model_copy(update={"name": "grantr.nope"})
    with pytest.raises(ValueError, match=r"grantr\.nope isn't one of grantr's commands"):
        await bound.call(other, {}, _context())


async def test_through_the_enforcer_an_admin_high_command_waits_for_its_callers_confirmation() -> (
    None
):
    capabilities = [c.capability for c in COMMANDS.values()]
    known = registry(*KNOWN_SETTINGS.values(), admin_high_approvers(capabilities))
    grants = Grants(InMemoryStorage(), catalogs=[ARTIFACTR], settings=known)
    await grants.first_operator(ROOT.id)
    await grants.create_tenant("acme", owner=ALICE.id, by=ROOT)
    enforcer = Enforcer(
        Registry(provider(grants)),
        integrations=grants,
        authorize=grants.authorize(),
        ceilings=FixedCeilings(),
        settings=grants,
        counter=FakeCounter(),
        taint=FixedTaint(),
        approvals=SettingsPolicy(grants),
        coverage=NoCoverage(),
        store=grants.approvals(),
        audit=grants.capability_audit(),
    )
    listed = await enforcer.call("grantr.list_members", {}, _context())
    assert {"kind": "user", "id": "alice"} in _parsed(listed.result.output)
    with pytest.raises(ApprovalPending) as pending:
        await enforcer.call("grantr.delete_tenant", {}, _context())
    approval = await grants.approvals().get(pending.value.approval)
    assert approval.answerers == Answerers(subjects=frozenset({"alice"}), confirmation=True)
    assert await grants.tenants(by=ROOT) == ["acme"], "nothing deleted until confirmed"
    with pytest.raises(Forbidden, match="grantr:delete_tenant"):
        await enforcer.call("grantr.delete_tenant", {}, _context(PersonCaller(id="bob")))
