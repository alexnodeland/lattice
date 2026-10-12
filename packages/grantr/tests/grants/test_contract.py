"""The contract: what grantr does, over every storage.

Each test runs against every storage ``conftest.storage_factory`` makes. The first three are the
exit criteria of grantr RFC-0001's phase 2.
"""

import asyncio

import pytest

from grantr.core import (
    DEPLOYMENT,
    TENANT,
    Agent,
    Forbidden,
    Grant,
    Granted,
    Grantee,
    Group,
    GroupDefined,
    GroupDeleted,
    Invalid,
    KeyIssued,
    KeyRevoked,
    Member,
    MemberAdded,
    MemberRemoved,
    Membership,
    Resource,
    Restricted,
    Revoked,
    Role,
    RoleDefined,
    RoleDeleted,
    RulePrincipal,
    ServicePrincipal,
    TenantCreated,
    TenantDeleted,
    Unrestricted,
    User,
    key_id,
)
from grantr.core.roles import RESTRICT
from grantr.grants import Grants, Storage
from tests.catalogs import ARTIFACTR, REFLEXR
from tests.grants.conftest import ALICE, NOW, ROOT

WS = Resource(kind="workspace", workspace="w1")
OTHER = Resource(kind="workspace", workspace="w2")
THREAD = Resource(kind="thread", workspace="w1", id="t1")
ARTIFACT = Resource(kind="artifact", workspace="w1", id="a1")
RULE = Resource(kind="rule", workspace="w1", id="ops:page")
BOB = User(id="bob")
CAROL = User(id="carol")
CI = ServicePrincipal(id="ci")
TEAM = Group(id="team")
TRIAGE = Role(name="triage", actions=frozenset({"reflexr:read_runs", "reflexr:cancel_run"}))


async def _members(grants: Grants, *members: User | ServicePrincipal) -> None:
    for member in members:
        await grants.add_member("acme", member, by=ALICE)


def _id(key: str) -> str:
    found = key_id(key)
    assert found
    return found


# ─── the exit criteria ───────────────────────────────────────────────────────


async def test_a_viewer_is_refused_an_edit(grants: Grants) -> None:
    await _members(grants, BOB)
    await grants.grant("acme", "viewer", on=WS, to=BOB, by=ALICE)
    assert await grants.check("acme", BOB, "artifactr:read_artifacts", ARTIFACT)
    assert await grants.check("acme", BOB, "artifactr:give_feedback", ARTIFACT)
    assert not await grants.check("acme", BOB, "artifactr:edit_artifact", ARTIFACT)
    assert not await grants.check("acme", BOB, "artifactr:read_artifacts", OTHER)


async def test_a_key_cant_reach_another_tenant(grants: Grants) -> None:
    await grants.create_tenant("globex", owner=CAROL.id, by=ROOT)
    await _members(grants, CI)
    await grants.grant("acme", "editor", on=WS, to=CI, by=ALICE)
    key, _ = await grants.issue_key("acme", CI, by=ALICE)

    assert await grants.authenticate(key) == ("acme", CI)
    assert await grants.check("acme", CI, "artifactr:edit_artifact", ARTIFACT)
    assert not await grants.check("globex", CI, "artifactr:read_artifacts", ARTIFACT)
    with pytest.raises(Invalid, match="globex has no key"):
        await grants.revoke_key("globex", _id(key), by=CAROL)

    await grants.add_member("globex", CI, by=CAROL)
    theirs, _ = await grants.issue_key("globex", CI, by=CAROL)
    assert await grants.authenticate(theirs) == ("globex", CI)
    assert await grants.authenticate(key) == ("acme", CI)


async def test_no_one_grants_more_than_they_hold(grants: Grants) -> None:
    await _members(grants, BOB, CAROL, CI)
    await grants.grant("acme", "admin", on=TENANT, to=BOB, by=ALICE)
    with pytest.raises(Forbidden, match="grantr:delete_tenant"):
        await grants.grant("acme", "owner", on=TENANT, to=CAROL, by=BOB)
    with pytest.raises(Forbidden, match="grantr:delete_tenant"):
        await grants.revoke("acme", "owner", on=TENANT, to=ALICE, by=BOB)
    with pytest.raises(Forbidden, match="grantr:delete_tenant"):
        await grants.remove_member("acme", ALICE, by=BOB)

    await grants.define_group("acme", TEAM, frozenset(), by=ALICE)
    await grants.grant("acme", "owner", on=TENANT, to=TEAM, by=ALICE)
    with pytest.raises(Forbidden, match="grantr:delete_tenant"):
        await grants.define_group("acme", TEAM, frozenset((BOB,)), by=BOB)
    await grants.grant("acme", "owner", on=TENANT, to=CI, by=ALICE)
    with pytest.raises(Forbidden, match="grantr:delete_tenant"):
        await grants.issue_key("acme", CI, by=BOB)
    key, _ = await grants.issue_key("acme", CI, by=ALICE)
    with pytest.raises(Forbidden, match="grantr:delete_tenant"):
        await grants.revoke_key("acme", _id(key), by=BOB)

    await grants.revoke("acme", "admin", on=TENANT, to=BOB, by=ALICE)
    await grants.grant("acme", "admin", on=WS, to=BOB, by=ALICE)
    await grants.grant("acme", "editor", on=THREAD, to=CAROL, by=BOB)
    with pytest.raises(Forbidden, match="grantr:grant on the tenant"):
        await grants.grant("acme", "admin", on=TENANT, to=CAROL, by=BOB)
    with pytest.raises(Forbidden, match="grantr:grant on the workspace"):
        await grants.grant("acme", "viewer", on=OTHER, to=CAROL, by=BOB)
    with pytest.raises(Forbidden, match="grantr:grant on the workspace"):
        await grants.grant("acme", "viewer", on=WS, to=BOB, by=CAROL)

    await grants.define_role(
        "acme", Role(name="granter", actions=frozenset({"grantr:grant"})), by=ALICE
    )
    await grants.grant("acme", "granter", on=OTHER, to=CAROL, by=ALICE)
    with pytest.raises(Forbidden, match="holds less than viewer gives: artifactr:give_feedback"):
        await grants.grant("acme", "viewer", on=OTHER, to=CI, by=CAROL)


# ─── checks ──────────────────────────────────────────────────────────────────


async def test_checks_deny_by_default(grants: Grants) -> None:
    await _members(grants, BOB)
    assert not await grants.check("acme", BOB, "artifactr:read_artifacts", WS)
    assert not await grants.check("acme", ALICE, "artifactr:fly", WS)
    assert not await grants.check("acme", Agent(), "artifactr:read_artifacts", WS)
    assert not await grants.check("globex", ALICE, "artifactr:read_artifacts", WS)
    assert await grants.check("acme", ALICE, "artifactr:read_artifacts", WS)


async def test_an_items_grants_add_to_its_workspaces(grants: Grants) -> None:
    await _members(grants, BOB)
    await grants.grant("acme", "viewer", on=WS, to=BOB, by=ALICE)
    await grants.grant("acme", "editor", on=THREAD, to=BOB, by=ALICE)
    assert await grants.check("acme", BOB, "artifactr:post_message", THREAD)
    assert not await grants.check(
        "acme", BOB, "artifactr:post_message", Resource(kind="thread", workspace="w1", id="t2")
    )


async def test_a_groups_members_hold_its_grants(grants: Grants) -> None:
    await _members(grants, BOB, CI)
    await grants.define_group(
        "acme",
        TEAM,
        frozenset(
            (
                BOB,
                CI,
            )
        ),
        by=ALICE,
    )
    await grants.grant("acme", "editor", on=WS, to=TEAM, by=ALICE)
    assert await grants.check("acme", BOB, "artifactr:edit_artifact", ARTIFACT)
    assert await grants.check("acme", CI, "artifactr:edit_artifact", ARTIFACT)

    await grants.define_group("acme", TEAM, frozenset((CI,)), by=ALICE)
    assert not await grants.check("acme", BOB, "artifactr:edit_artifact", ARTIFACT)
    await grants.delete_group("acme", TEAM, by=ALICE)
    assert not await grants.check("acme", CI, "artifactr:edit_artifact", ARTIFACT)


async def test_a_custom_role_holds_its_actions_where_it_is_granted(grants: Grants) -> None:
    await _members(grants, BOB)
    await grants.define_role("acme", TRIAGE, by=ALICE)
    await grants.grant("acme", "triage", on=RULE, to=BOB, by=ALICE)
    assert await grants.check("acme", BOB, "reflexr:cancel_run", RULE)
    assert not await grants.check("acme", BOB, "reflexr:cancel_run", WS)
    with pytest.raises(Invalid, match="triage can't be granted on a tenant"):
        await grants.grant("acme", "triage", on=TENANT, to=BOB, by=ALICE)

    await grants.define_role(
        "acme", Role(name="triage", actions=frozenset({"reflexr:read_runs"})), by=ALICE
    )
    assert not await grants.check("acme", BOB, "reflexr:cancel_run", RULE)
    assert await grants.check("acme", BOB, "reflexr:read_runs", RULE)
    await grants.delete_role("acme", "triage", by=ALICE)
    assert not await grants.check("acme", BOB, "reflexr:read_runs", RULE)
    with pytest.raises(Invalid, match="no custom role triage"):
        await grants.delete_role("acme", "triage", by=ALICE)
    with pytest.raises(Invalid, match="built-in"):
        await grants.define_role(
            "acme", Role(name="viewer", actions=frozenset({"artifactr:open"})), by=ALICE
        )


async def test_a_rule_holds_what_it_is_granted(grants: Grants) -> None:
    rule = RulePrincipal(workspace="w1", rule="ops:page")
    assert not await grants.check("acme", rule, "reflexr:cancel_run", WS)
    await grants.grant("acme", "editor", on=WS, to=rule, by=ALICE)
    assert await grants.check("acme", rule, "reflexr:cancel_run", WS)


async def test_tenant_roles_reach_every_workspace_and_every_catalog(grants: Grants) -> None:
    assert await grants.check("acme", ALICE, "reflexr:install_rule", RULE)
    assert await grants.check("acme", ALICE, "portalr:read_telemetry", TENANT)
    assert await grants.check("acme", ALICE, "reflexr:read_rules", TENANT)


async def test_resources_lists_what_a_subject_may_act_on(grants: Grants) -> None:
    await _members(grants, BOB)
    await grants.grant("acme", "viewer", on=WS, to=BOB, by=ALICE)
    await grants.grant(
        "acme", "editor", on=Resource(kind="artifact", workspace="w2", id="a9"), to=BOB, by=ALICE
    )
    assert await grants.resources("acme", BOB, "artifactr:open", "workspace") == [WS]
    assert await grants.resources("acme", ALICE, "artifactr:open", "workspace") == [WS, OTHER]
    assert await grants.resources("acme", BOB, "artifactr:edit_artifact", "artifact") == [
        Resource(kind="artifact", workspace="w2", id="a9")
    ]
    assert await grants.resources("acme", ALICE, "artifactr:fly", "workspace") == []
    assert await grants.resources("acme", Agent(), "artifactr:open", "workspace") == []


async def test_a_restricted_thread_is_hidden_from_a_non_member(grants: Grants) -> None:
    await _members(grants, BOB, CAROL)
    await grants.grant("acme", "editor", on=WS, to=BOB, by=ALICE)
    await grants.grant("acme", "viewer", on=THREAD, to=CAROL, by=ALICE)
    assert await grants.check("acme", BOB, "artifactr:read_threads", THREAD)

    entry = await grants.restrict("acme", THREAD, by=ALICE)

    assert entry.event == Restricted(on=THREAD)
    assert not await grants.check("acme", BOB, "artifactr:read_threads", THREAD)
    assert await grants.check(
        "acme", BOB, "artifactr:read_threads", Resource(kind="thread", workspace="w1", id="t2")
    ), "only the restricted thread is hidden"
    assert await grants.check("acme", CAROL, "artifactr:read_threads", THREAD)
    assert await grants.check("acme", ALICE, "artifactr:read_threads", THREAD)
    assert (await grants.hidden("acme", BOB, "w1")).threads == {"t1"}
    assert (await grants.hidden("acme", BOB, "w2")).threads == frozenset()
    assert (await grants.hidden("acme", CAROL, "w1")).threads == frozenset()
    assert (await grants.hidden("acme", ALICE, "w1")).threads == frozenset()
    assert (await grants.hidden("acme", Agent(), "w1")).threads == {"t1"}
    assert await grants.resources("acme", BOB, "artifactr:read_threads", "thread") == []
    assert await grants.resources("acme", CAROL, "artifactr:read_threads", "thread") == [THREAD]

    lifted = await grants.restrict("acme", THREAD, restricted=False, by=ALICE)

    assert lifted.event == Unrestricted(on=THREAD)
    assert await grants.check("acme", BOB, "artifactr:read_threads", THREAD)
    assert (await grants.hidden("acme", BOB, "w1")).threads == frozenset()


async def test_a_workspace_admin_restricts_and_sees_what_is_restricted(grants: Grants) -> None:
    await _members(grants, BOB, CAROL)
    await grants.grant("acme", "admin", on=WS, to=BOB, by=ALICE)
    await grants.grant("acme", "editor", on=WS, to=CAROL, by=ALICE)

    await grants.restrict("acme", ARTIFACT, by=BOB)

    assert await grants.check("acme", BOB, "artifactr:edit_artifact", ARTIFACT)
    assert not await grants.check("acme", CAROL, "artifactr:edit_artifact", ARTIFACT)
    assert (await grants.hidden("acme", CAROL, "w1")).artifacts == {"a1"}
    assert await grants.restrictions("acme", "w1", by=BOB) == [ARTIFACT]
    assert await grants.restrictions("acme", "w2", by=ALICE) == []
    with pytest.raises(Forbidden, match="grantr:restrict"):
        await grants.restrictions("acme", "w1", by=CAROL)
    with pytest.raises(Forbidden, match="grantr:restrict"):
        await grants.restrict("acme", THREAD, by=CAROL)


async def test_who_sees_a_restricted_thread_beyond_its_built_in_roles(grants: Grants) -> None:
    dave, erin, rule = User(id="dave"), User(id="erin"), RulePrincipal(workspace="w1", rule="r")
    await _members(grants, BOB, CAROL, dave, erin)
    await grants.define_group("acme", TEAM, frozenset[Member]().union((CAROL,)), by=ALICE)
    await grants.grant("acme", "viewer", on=THREAD, to=TEAM, by=ALICE)
    await grants.grant("acme", "admin", on=TENANT, to=BOB, by=ALICE)
    reads = frozenset({"artifactr:read_threads"})
    for name, actions, to in (("reader", reads, dave), ("curator", reads | {RESTRICT}, erin)):
        await grants.define_role("acme", Role(name=name, actions=actions), by=ALICE)
        await grants.grant("acme", name, on=WS, to=to, by=ALICE)
    await grants.grant("acme", "rule", on=WS, to=rule, by=ALICE)

    await grants.restrict("acme", THREAD, by=ALICE)

    read = "artifactr:read_threads"
    seen = [await grants.check("acme", who, read, THREAD) for who in (BOB, CAROL, dave, erin)]
    assert seen == [True, True, False, True], "the tenant's admin, a group, a reader, a curator"
    assert not await grants.check("acme", rule, "reflexr:read_runs", THREAD)
    assert (await grants.hidden("acme", CAROL, "w1")).threads == frozenset(), "by its group"
    assert (await grants.hidden("acme", dave, "w1")).threads == {"t1"}
    assert (await grants.hidden("acme", rule, "w1")).threads == {"t1"}


async def test_only_a_thread_or_artifact_is_restricted_and_only_once(grants: Grants) -> None:
    with pytest.raises(Invalid, match="a workspace isn't restricted"):
        await grants.restrict("acme", WS, by=ALICE)
    with pytest.raises(Invalid, match="not restricted already"):
        await grants.restrict("acme", THREAD, restricted=False, by=ALICE)
    await grants.restrict("acme", THREAD, by=ALICE)
    with pytest.raises(Invalid, match="is restricted already"):
        await grants.restrict("acme", THREAD, by=ALICE)
    assert [e.event.type for e in await grants.audit("acme", by=ALICE)][-1] == "restricted"


async def test_restrictions_go_with_their_tenant(grants: Grants) -> None:
    await grants.restrict("acme", THREAD, by=ALICE)
    await grants.delete_tenant("acme", by=ALICE)
    await grants.create_tenant("acme", owner=CAROL.id, by=ROOT)
    assert await grants.restrictions("acme", "w1", by=CAROL) == []


# ─── tenants, members and operators ──────────────────────────────────────────


async def test_an_operator_creates_tenants_and_sees_none_of_their_workspaces(
    grants: Grants,
) -> None:
    assert not await grants.check("acme", ROOT, "artifactr:read_artifacts", WS)
    with pytest.raises(Forbidden, match="grantr:create_tenant"):
        await grants.create_tenant("globex", owner=BOB.id, by=ALICE)
    with pytest.raises(Invalid, match="acme exists"):
        await grants.create_tenant("acme", owner=BOB.id, by=ROOT)


async def test_an_operator_grants_themselves_a_role_in_a_tenant(grants: Grants) -> None:
    assert not await grants.check("acme", ROOT, "artifactr:read_artifacts", WS)
    await grants.grant("acme", "viewer", on=WS, to=ROOT, by=ROOT)
    assert await grants.check("acme", ROOT, "artifactr:read_artifacts", WS)
    assert await grants.member("acme", ROOT.id) is not None
    entries = (await grants.audit("acme", by=ALICE))[-2:]
    assert [(entry.by, type(entry.event)) for entry in entries] == [
        (ROOT, MemberAdded),
        (ROOT, Granted),
    ]
    await grants.grant("acme", "admin", on=TENANT, to=ROOT, by=ROOT)
    assert [type(e.event) for e in await grants.audit("acme", by=ALICE)][-2:] == [Granted, Granted]
    with pytest.raises(Invalid, match="no tenant globex"):
        await grants.grant("globex", "viewer", on=WS, to=ROOT, by=ROOT)
    with pytest.raises(Forbidden, match="grantr:grant on the tenant"):
        await grants.grant("acme", "admin", on=TENANT, to=BOB, by=CAROL)


async def test_anyone_may_give_up_their_own_grant(grants: Grants) -> None:
    await _members(grants, BOB)
    await grants.grant("acme", "editor", on=WS, to=BOB, by=ALICE)
    await grants.revoke("acme", "editor", on=WS, to=BOB, by=BOB)
    assert not await grants.check("acme", BOB, "artifactr:edit_artifact", WS)


async def test_the_last_owner_stays(grants: Grants) -> None:
    with pytest.raises(Invalid, match="is the last owner"):
        await grants.revoke("acme", "owner", on=TENANT, to=ALICE, by=ALICE)
    with pytest.raises(Invalid, match="is the last owner"):
        await grants.remove_member("acme", ALICE, by=ALICE)
    await _members(grants, BOB)
    await grants.define_group("acme", TEAM, frozenset((BOB,)), by=ALICE)
    await grants.grant("acme", "owner", on=TENANT, to=TEAM, by=ALICE)
    await grants.revoke("acme", "owner", on=TENANT, to=ALICE, by=ALICE)
    with pytest.raises(Invalid, match="is the last owner"):
        await grants.delete_group("acme", TEAM, by=BOB)
    assert await grants.check("acme", BOB, "grantr:delete_tenant", TENANT)


async def test_operators_are_granted_by_operators(grants: Grants) -> None:
    with pytest.raises(Invalid, match="has an operator already"):
        await grants.first_operator(BOB.id)
    with pytest.raises(Forbidden, match="grantr:grant_operator"):
        await grants.grant_operator(BOB.id, by=ALICE)
    await grants.grant_operator(BOB.id, by=ROOT)
    with pytest.raises(Invalid, match="is an operator already"):
        await grants.grant_operator(BOB.id, by=ROOT)
    await grants.create_tenant("globex", owner=CAROL.id, by=BOB)
    await grants.revoke_operator(BOB.id, by=ROOT)
    with pytest.raises(Invalid, match="isn't an operator"):
        await grants.revoke_operator(BOB.id, by=ROOT)
    with pytest.raises(Forbidden):
        await grants.create_tenant("initech", owner=CAROL.id, by=BOB)


async def test_the_deployments_role_and_membership_have_their_own_commands(grants: Grants) -> None:
    await _members(grants, BOB)
    with pytest.raises(Invalid, match="grant_operator"):
        await grants.grant("acme", "operator", on=DEPLOYMENT, to=BOB, by=ALICE)
    with pytest.raises(Invalid, match="add_member"):
        await grants.revoke("acme", "member", on=TENANT, to=BOB, by=ALICE)


async def test_members_and_memberships(grants: Grants) -> None:
    await grants.create_tenant("globex", owner=BOB.id, by=ROOT)
    await _members(grants, BOB)
    assert await grants.member("acme", ALICE.id) == Membership(
        tenant="acme", user="alice", roles=("member", "owner")
    )
    assert await grants.member("acme", BOB.id) == Membership(
        tenant="acme", user="bob", roles=("member",)
    )
    assert await grants.member("acme", CAROL.id) is None
    assert await grants.memberships(BOB.id) == [
        Membership(tenant="acme", user="bob", roles=("member",)),
        Membership(tenant="globex", user="bob", roles=("member", "owner")),
    ]
    with pytest.raises(Invalid, match="is a member already"):
        await grants.add_member("acme", BOB, by=ALICE)
    with pytest.raises(Forbidden, match="grantr:add_member"):
        await grants.add_member("acme", CAROL, by=BOB)


async def test_only_members_are_granted_roles_or_join_groups(grants: Grants) -> None:
    with pytest.raises(Invalid, match="isn't a member"):
        await grants.grant("acme", "viewer", on=WS, to=BOB, by=ALICE)
    with pytest.raises(Invalid, match="isn't a member"):
        await grants.define_group("acme", TEAM, frozenset((BOB,)), by=ALICE)
    with pytest.raises(Invalid, match="no group team"):
        await grants.grant("acme", "viewer", on=WS, to=TEAM, by=ALICE)
    with pytest.raises(Invalid, match="no group team"):
        await grants.delete_group("acme", TEAM, by=ALICE)
    with pytest.raises(Invalid, match="isn't a member"):
        await grants.issue_key("acme", CI, by=ALICE)
    with pytest.raises(Invalid, match="isn't a member"):
        await grants.remove_member("acme", BOB, by=ALICE)


async def test_a_grant_is_given_once_and_revoked_once(grants: Grants) -> None:
    await _members(grants, BOB)
    await grants.grant("acme", "viewer", on=WS, to=BOB, by=ALICE)
    with pytest.raises(Invalid, match="holds viewer there already"):
        await grants.grant("acme", "viewer", on=WS, to=BOB, by=ALICE)
    await grants.revoke("acme", "viewer", on=WS, to=BOB, by=ALICE)
    with pytest.raises(Invalid, match="doesn't hold viewer there"):
        await grants.revoke("acme", "viewer", on=WS, to=BOB, by=ALICE)
    with pytest.raises(Invalid, match="owner can't be granted on a workspace"):
        await grants.grant("acme", "owner", on=WS, to=BOB, by=ALICE)


async def test_removing_a_member_takes_its_grants_groups_and_keys(grants: Grants) -> None:
    await _members(grants, BOB, CI)
    await grants.define_group(
        "acme",
        TEAM,
        frozenset(
            (
                BOB,
                CI,
            )
        ),
        by=ALICE,
    )
    await grants.grant("acme", "editor", on=WS, to=TEAM, by=ALICE)
    await grants.grant("acme", "viewer", on=OTHER, to=CI, by=ALICE)
    key, _ = await grants.issue_key("acme", CI, by=ALICE)

    await grants.remove_member("acme", CI, by=ALICE)
    assert await grants.authenticate(key) is None
    assert not await grants.check("acme", CI, "artifactr:read_artifacts", OTHER)
    assert not await grants.check("acme", CI, "artifactr:read_artifacts", WS)
    assert await grants.check("acme", BOB, "artifactr:read_artifacts", WS)


async def test_deleting_a_tenant_leaves_only_its_audit_log(grants: Grants) -> None:
    await _members(grants, BOB, CI)
    await grants.grant("acme", "admin", on=TENANT, to=BOB, by=ALICE)
    key, _ = await grants.issue_key("acme", CI, by=ALICE)
    with pytest.raises(Forbidden, match="grantr:delete_tenant"):
        await grants.delete_tenant("acme", by=BOB)
    await grants.delete_tenant("acme", by=ALICE)

    assert await grants.member("acme", ALICE.id) is None
    assert await grants.authenticate(key) is None
    await grants.create_tenant("acme", owner=CAROL.id, by=ROOT)
    assert not await grants.check("acme", BOB, "artifactr:read_artifacts", WS)
    events = [entry.event for entry in await grants.audit("acme", by=CAROL)]
    assert [type(event) for event in events][-3:] == [KeyIssued, TenantDeleted, TenantCreated]


# ─── keys ────────────────────────────────────────────────────────────────────


async def test_a_revoked_key_authenticates_nothing(grants: Grants) -> None:
    await _members(grants, CI)
    key, _ = await grants.issue_key("acme", CI, by=ALICE)
    entry = await grants.revoke_key("acme", _id(key), by=ALICE)
    assert entry.event == KeyRevoked(principal=CI, key=_id(key))
    assert await grants.authenticate(key) is None
    assert await grants.authenticate("not a key") is None
    with pytest.raises(Invalid, match="acme has no key"):
        await grants.revoke_key("acme", _id(key), by=ALICE)


# ─── the audit log ───────────────────────────────────────────────────────────


async def test_every_change_is_in_the_audit_log_in_order(grants: Grants) -> None:
    await _members(grants, BOB)
    await grants.define_group("acme", TEAM, frozenset((BOB,)), by=ALICE)
    await grants.define_role("acme", TRIAGE, by=ALICE)
    await grants.grant("acme", "triage", on=WS, to=TEAM, by=ALICE)
    await grants.revoke("acme", "triage", on=WS, to=TEAM, by=ALICE)
    await grants.delete_role("acme", "triage", by=ALICE)
    await grants.delete_group("acme", TEAM, by=ALICE)
    await grants.remove_member("acme", BOB, by=ALICE)

    entries = await grants.audit("acme", by=ALICE)
    grant = Grant(tenant="acme", role="triage", on=WS, to=TEAM)
    assert [entry.event for entry in entries] == [
        TenantCreated(owner="alice"),
        MemberAdded(member=BOB),
        GroupDefined(group="team", members=frozenset((BOB,))),
        RoleDefined(role=TRIAGE),
        Granted(grant=grant),
        Revoked(grant=grant),
        RoleDeleted(role="triage"),
        GroupDeleted(group="team"),
        MemberRemoved(member=BOB),
    ]
    assert all(entry.tenant == "acme" and entry.at == NOW for entry in entries)
    assert [entry.by for entry in entries] == [ROOT] + [ALICE] * 8
    assert [entry.seq for entry in entries] == list(range(2, 11)), "one log; 1 is the operator's"

    page = await grants.audit("acme", by=ALICE, after_seq=entries[2].seq, limit=2)
    assert page == entries[3:5]


async def test_the_deployments_log_holds_its_operators(grants: Grants) -> None:
    await grants.grant_operator(BOB.id, by=ROOT)
    entries = await grants.audit(None, by=ROOT)
    assert [(entry.by, entry.event) for entry in entries] == [
        (None, Granted(grant=Grant(tenant=None, role="operator", on=DEPLOYMENT, to=ROOT))),
        (ROOT, Granted(grant=Grant(tenant=None, role="operator", on=DEPLOYMENT, to=BOB))),
    ]
    with pytest.raises(Forbidden, match="grantr:grant_operator"):
        await grants.audit(None, by=ALICE)
    with pytest.raises(Forbidden, match="grantr:read_audit"):
        await grants.audit("acme", by=ROOT)


# ─── the storage ─────────────────────────────────────────────────────────────


async def test_a_transaction_that_raises_leaves_nothing(storage: Storage) -> None:
    async def change_then_raise() -> None:
        async with storage.transaction("acme") as tx:
            await tx.create_tenant("acme")
            await tx.add_grant(Grant(tenant="acme", role="viewer", on=WS, to=BOB))
            await tx.append("acme", ALICE, MemberAdded(member=BOB))
            assert await tx.tenant("acme")
            raise RuntimeError

    with pytest.raises(RuntimeError):
        await change_then_raise()
    assert not await storage.tenant("acme")
    assert await storage.granted("acme", WS) == []
    assert await storage.audit("acme") == []


async def test_a_storage_knows_the_resources_its_grants_name(storage: Storage) -> None:
    async with storage.transaction("acme") as tx:
        await tx.add_grant(Grant(tenant="acme", role="viewer", on=THREAD, to=BOB))
        await tx.add_grant(Grant(tenant="acme", role="viewer", on=OTHER, to=BOB))
        await tx.add_grant(Grant(tenant="globex", role="viewer", on=ARTIFACT, to=BOB))
    assert await storage.resources("acme", "workspace") == [WS, OTHER]
    assert await storage.resources("acme", "thread") == [THREAD]
    assert await storage.resources("acme", "artifact") == []


async def test_a_storage_reads_what_its_transactions_committed(storage: Storage) -> None:
    viewer = Grant(tenant="acme", role="viewer", on=WS, to=TEAM)
    async with storage.transaction("acme") as tx:
        await tx.create_tenant("acme")
        await tx.add_grant(viewer)
        await tx.put_group("acme", TEAM, frozenset((BOB,)))
        await tx.put_role("acme", TRIAGE)
    assert await storage.tenant("acme")
    assert await storage.has(viewer)
    assert await storage.grants("acme", BOB, on=[WS]) == [viewer]
    assert await storage.grants("acme", CAROL) == []
    assert await storage.group("acme", TEAM) == frozenset((BOB,))
    assert await storage.groups("acme") == {"team": frozenset((BOB,))}
    assert await storage.roles("acme") == {"triage": TRIAGE}
    assert await storage.grants_in("acme", workspace="w1") == [viewer]
    assert await storage.grants_in("acme", workspace="w2") == []
    assert await storage.tenants() == ["acme"]


# ─── what an admin lists ─────────────────────────────────────────────────────


async def test_an_admin_lists_what_they_manage(grants: Grants) -> None:
    await _members(grants, BOB, CI)
    await grants.define_group("acme", TEAM, frozenset((BOB,)), by=ALICE)
    await grants.define_group("acme", Group(id="empty"), frozenset(), by=ALICE)
    await grants.define_role("acme", TRIAGE, by=ALICE)
    await grants.grant("acme", "admin", on=WS, to=BOB, by=ALICE)
    await grants.grant("acme", "viewer", on=THREAD, to=CI, by=ALICE)
    key, _ = await grants.issue_key("acme", CI, by=ALICE)

    assert sorted(m.id for m in await grants.members("acme", by=ALICE)) == ["alice", "bob", "ci"]
    assert await grants.groups("acme", by=ALICE) == {
        "team": frozenset((BOB,)),
        "empty": frozenset(),
    }
    assert await grants.roles("acme", by=ALICE) == [TRIAGE]
    assert len(await grants.grants_in("acme", by=ALICE)) == 6
    in_w1 = await grants.grants_in("acme", by=BOB, workspace="w1")
    assert sorted((g.role, g.on.kind) for g in in_w1) == [
        ("admin", "workspace"),
        ("viewer", "thread"),
    ]
    assert [(k.id, k.principal) for k in await grants.keys("acme", by=ALICE)] == [(_id(key), CI)]

    for listing in (grants.members, grants.groups, grants.roles, grants.keys, grants.grants_in):
        with pytest.raises(Forbidden):
            await listing("acme", by=BOB)
    with pytest.raises(Forbidden, match="grantr:grant on the workspace"):
        await grants.grants_in("acme", by=BOB, workspace="w2")


async def test_an_operator_lists_the_tenants(grants: Grants) -> None:
    await grants.create_tenant("globex", owner=CAROL.id, by=ROOT)
    await grants.delete_tenant("globex", by=CAROL)
    await grants.create_tenant("initech", owner=CAROL.id, by=ROOT)
    assert await grants.tenants(by=ROOT) == ["acme", "initech"]
    with pytest.raises(Forbidden, match="grantr:create_tenant"):
        await grants.tenants(by=ALICE)
    with pytest.raises(Invalid, match="isn't empty"):
        await grants.create_tenant("", owner=CAROL.id, by=ROOT)


# ─── the application and the deployment's own tools ─────────────────────────

APP = ServicePrincipal(id="app")


async def test_the_application_holds_its_runtime_in_every_tenant_and_operators_dont(
    storage: Storage,
) -> None:
    grants = Grants(storage, catalogs=[ARTIFACTR, REFLEXR], application=APP)
    await grants.first_operator(ROOT.id)
    for tenant in ("acme", "globex"):
        await grants.provision_tenant(tenant, owner=ALICE.id)
    assert not await grants.check("acme", APP, "artifactr:claim_thread", THREAD)
    await grants.restrict("acme", THREAD, by=ALICE)
    assert (await grants.hidden("acme", APP, "w1")).threads == {"t1"}

    [entry] = await grants.bootstrap()
    assert (await grants.hidden("acme", APP, "w1")).threads == frozenset(), "it sees everything"
    assert (entry.by, entry.tenant) == (None, None)
    assert await grants.bootstrap() == [], "a second start changes nothing"
    for tenant in ("acme", "globex"):
        assert await grants.check(tenant, APP, "artifactr:claim_thread", THREAD)
        # reflexr asks a run's checkpoint of its workspace.
        assert await grants.check(tenant, APP, "reflexr:checkpoint_run", WS)
        assert not await grants.check(tenant, APP, "artifactr:edit_artifact", ARTIFACT)
        assert not await grants.check(tenant, ROOT, "artifactr:read_artifacts", WS)
    assert not await grants.check("acme", ServicePrincipal(id="other"), "artifactr:open", WS)


async def test_a_tenant_cant_borrow_the_applications_identity(storage: Storage) -> None:
    unconfigured = Grants(storage, catalogs=[ARTIFACTR])
    await unconfigured.provision_tenant("acme", owner=ALICE.id)
    await unconfigured.add_member("acme", APP, by=ALICE)
    await unconfigured.grant("acme", "viewer", on=WS, to=APP, by=ALICE)
    key, _ = await unconfigured.issue_key("acme", APP, by=ALICE)

    grants = Grants(storage, catalogs=[ARTIFACTR], application=APP)
    await grants.bootstrap()
    assert await grants.authenticate(key) is None, "a key for the application's id is no key"
    assert not await unconfigured.check("acme", APP, "artifactr:claim_thread", THREAD)
    with pytest.raises(Invalid, match="no tenant's member"):
        await grants.add_member("acme", APP, by=ALICE)


async def test_bootstrap_moves_the_role_to_the_configured_principal(storage: Storage) -> None:
    await Grants(storage, application=APP).bootstrap()
    renamed = ServicePrincipal(id="app-2")
    entries = await Grants(storage, application=renamed).bootstrap()
    assert [type(entry.event) for entry in entries] == [Revoked, Granted]
    assert await storage.granted(None, DEPLOYMENT, role="application") == [
        Grant(tenant=None, role="application", on=DEPLOYMENT, to=renamed)
    ]


async def test_replicas_starting_together_bootstrap_once(storage: Storage) -> None:
    replicas = [Grants(storage, application=APP) for _ in range(3)]
    started = await asyncio.gather(*(replica.bootstrap() for replica in replicas))
    assert sorted(len(entries) for entries in started) == [0, 0, 1]


async def test_only_a_configured_application_is_bootstrapped(grants: Grants) -> None:
    with pytest.raises(Invalid, match="no application principal"):
        await grants.bootstrap()


@pytest.mark.parametrize(("on", "to"), [(TENANT, BOB), (WS, BOB), (WS, TEAM), (DEPLOYMENT, BOB)])
async def test_no_one_grants_the_deployments_roles(
    grants: Grants, on: Resource, to: Grantee
) -> None:
    with pytest.raises(Invalid, match="given by grant_operator and bootstrap"):
        await grants.grant("acme", "application", on=on, to=to, by=ALICE)


async def test_the_deployments_tools_provision_a_tenant_and_the_admins_it_lacks(
    grants: Grants,
) -> None:
    admins = [BOB.id, CAROL.id, CAROL.id]
    entries = await grants.provision_tenant("globex", owner=BOB.id, admins=admins)
    assert [(entry.by, type(entry.event)) for entry in entries] == [
        (None, TenantCreated),
        (None, MemberAdded),
        (None, Granted),
    ]
    assert await grants.member("globex", BOB.id) == Membership(
        tenant="globex", user="bob", roles=("member", "owner")
    )
    assert await grants.member("globex", CAROL.id) == Membership(
        tenant="globex", user="carol", roles=("admin", "member")
    )
    assert await grants.provision_tenant("globex", owner=CAROL.id) == [], "the owner stays"
    again = await grants.provision_tenant("globex", owner=BOB.id, admins=[CAROL.id, "dave"])
    assert [type(entry.event) for entry in again] == [MemberAdded, Granted]
    assert await grants.member("globex", "dave") == Membership(
        tenant="globex", user="dave", roles=("admin", "member")
    )
    with pytest.raises(Invalid, match="has no ~"):
        await grants.provision_tenant("a~b", owner=BOB.id)


async def test_a_workspaces_admin_grants_a_stored_rule_its_role(grants: Grants) -> None:
    await _members(grants, BOB)
    await grants.grant("acme", "admin", on=WS, to=BOB, by=ALICE)
    rule = RulePrincipal(workspace="w1", rule="ops:page")
    with pytest.raises(Invalid, match="rule can't be granted on a rule"):
        await grants.grant("acme", "rule", on=RULE, to=rule, by=BOB)
    await grants.grant("acme", "rule", on=WS, to=rule, by=BOB)
    # reflexr asks a run's publishing and checkpoints of the workspace, naming no rule.
    assert await grants.check("acme", rule, "reflexr:publish", WS)
    assert await grants.check("acme", rule, "reflexr:checkpoint_run", WS)
    assert not await grants.check("acme", rule, "reflexr:install_rule", RULE)
