"""The admin API, over HTTP: each command and list, /me, /checks, and the shapes of refusals."""

import httpx
import pytest

from grantr.core import Resource, User
from grantr.grants import Grants
from tests.fastapi.conftest import ALICE, ROOT

AS_ALICE = {"X-User": "alice"}
AS_ROOT = {"X-User": "root"}
AS_BOB = {"X-User": "bob"}
WS = {"kind": "workspace", "workspace": "w1"}
BOB = {"kind": "user", "id": "bob"}


async def test_no_caller_is_401(client: httpx.AsyncClient) -> None:
    assert (await client.get("/me")).json() == {
        "detail": {"type": "unauthorized", "message": "no caller"}
    }
    response = await client.get("/me", headers={"X-Api-Key": "grantr_sk_x"})
    assert response.status_code == 401
    assert response.json() == {"detail": {"type": "unauthorized", "message": "unknown key"}}


async def test_an_owner_manages_a_tenant(client: httpx.AsyncClient) -> None:
    created = await client.post("/tenants/acme/members", json={"member": BOB}, headers=AS_ALICE)
    assert created.status_code == 201
    assert created.json()["event"] == {"type": "member_added", "member": BOB}
    grant = {"role": "editor", "on": WS, "to": BOB}
    assert (
        await client.post("/tenants/acme/grants", json=grant, headers=AS_ALICE)
    ).status_code == 201
    listed = await client.get("/tenants/acme/grants", params={"workspace": "w1"}, headers=AS_ALICE)
    assert [g["role"] for g in listed.json()] == ["editor"]
    revoked = await client.post("/tenants/acme/revocations", json=grant, headers=AS_ALICE)
    assert revoked.json()["event"]["type"] == "revoked"

    members = await client.get("/tenants/acme/members", headers=AS_ALICE)
    assert sorted(m["id"] for m in members.json()) == ["alice", "bob"]
    group = await client.put("/tenants/acme/groups/team", json={"members": [BOB]}, headers=AS_ALICE)
    assert group.json()["event"]["type"] == "group_defined"
    groups = await client.get("/tenants/acme/groups", headers=AS_ALICE)
    assert groups.json() == {"team": [BOB]}
    assert (await client.delete("/tenants/acme/groups/team", headers=AS_ALICE)).status_code == 200

    role = await client.put(
        "/tenants/acme/roles/triage", json={"actions": ["artifactr:open"]}, headers=AS_ALICE
    )
    assert role.json()["event"]["role"] == {"name": "triage", "actions": ["artifactr:open"]}
    roles = await client.get("/tenants/acme/roles", headers=AS_ALICE)
    assert roles.json() == [{"name": "triage", "actions": ["artifactr:open"]}]
    assert (await client.delete("/tenants/acme/roles/triage", headers=AS_ALICE)).status_code == 200

    removed = await client.delete("/tenants/acme/members/user/bob", headers=AS_ALICE)
    assert removed.json()["event"]["type"] == "member_removed"
    audit = await client.get("/tenants/acme/audit", params={"after_seq": 2}, headers=AS_ALICE)
    assert [e["event"]["type"] for e in audit.json()] == [
        "member_added",
        "granted",
        "revoked",
        "group_defined",
        "group_deleted",
        "role_defined",
        "role_deleted",
        "member_removed",
    ]


async def test_keys_are_shown_once_and_bound_to_their_tenant(client: httpx.AsyncClient) -> None:
    ci = {"kind": "service_principal", "id": "ci"}
    await client.post("/tenants/acme/members", json={"member": ci}, headers=AS_ALICE)
    await client.post(
        "/tenants/acme/grants", json={"role": "viewer", "on": WS, "to": ci}, headers=AS_ALICE
    )
    issued = (
        await client.post("/tenants/acme/keys", json={"principal": "ci"}, headers=AS_ALICE)
    ).json()
    listed = (await client.get("/tenants/acme/keys", headers=AS_ALICE)).json()
    assert listed == [{"id": issued["entry"]["event"]["key"], "principal": ci}]
    assert issued["key"] not in str(listed)

    as_key = {"X-Api-Key": issued["key"]}
    me = await client.get("/me", headers=as_key)
    assert me.json() == {"tenant": "acme", "roles": ["member"], "workspaces": ["w1"]}
    elsewhere = await client.get("/tenants/globex/members", headers=as_key)
    assert elsewhere.status_code == 403
    assert elsewhere.json()["detail"]["type"] == "forbidden"
    assert (await client.get("/me", headers={**as_key, "X-Tenant": "globex"})).status_code == 403

    key_id = listed[0]["id"]
    assert (
        await client.delete(f"/tenants/acme/keys/{key_id}", headers=AS_ALICE)
    ).status_code == 200
    gone = await client.delete("/tenants/acme/members/service_principal/ci", headers=AS_ALICE)
    assert gone.json()["event"]["member"] == ci


async def test_operators_list_create_and_delete_tenants(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/tenants", json={"tenant": "globex", "owner": "bob"}, headers=AS_ROOT
    )
    assert created.status_code == 201
    assert (await client.get("/tenants", headers=AS_ROOT)).json() == ["acme", "globex"]
    assert (await client.put("/operators/carol", headers=AS_ROOT)).status_code == 200
    assert (await client.delete("/operators/carol", headers=AS_ROOT)).status_code == 200
    audit = (await client.get("/audit", headers=AS_ROOT)).json()
    assert [(e["event"]["type"], e["tenant"]) for e in audit] == [
        ("granted", None),
        ("deployment_tenant_created", None),
        ("deployment_tenant_created", None),
        ("granted", None),
        ("revoked", None),
    ]
    assert [e["event"]["tenant"] for e in audit if e["event"]["type"].startswith("deployment")] == [
        "acme",
        "globex",
    ]
    assert (await client.delete("/tenants/globex", headers=AS_BOB)).status_code == 200


async def test_refusals_keep_the_libraries_shapes(client: httpx.AsyncClient) -> None:
    forbidden = await client.get("/tenants", headers=AS_ALICE)
    assert (forbidden.status_code, forbidden.json()["detail"]["type"]) == (403, "forbidden")
    invalid = await client.post(
        "/tenants/acme/members", json={"member": {"kind": "user", "id": "alice"}}, headers=AS_ALICE
    )
    assert (invalid.status_code, invalid.json()["detail"]["type"]) == (422, "invalid")
    assert "is a member already" in invalid.json()["detail"]["message"]


async def test_me_and_checks(client: httpx.AsyncClient, grants: Grants) -> None:
    assert (await client.get("/me", headers=AS_ALICE)).json() == {
        "memberships": [{"tenant": "acme", "user": "alice", "roles": ["member", "owner"]}]
    }
    assert (await client.get("/me", headers=AS_BOB)).json() == {"memberships": []}

    questions = [
        {"action": "artifactr:open", "resource": WS},
        {"action": "grantr:create_tenant", "resource": {"kind": "deployment"}},
    ]
    answers = await client.post("/checks", json=questions, headers=AS_ALICE)
    assert answers.json() == [True, False]
    await grants.add_member("acme", User(id="bob"), by=ALICE)
    await grants.grant(
        "acme", "viewer", on=Resource(kind="workspace", workspace="w1"), to=User(id="bob"), by=ALICE
    )
    me = await client.get("/me", headers={**AS_BOB, "X-Tenant": "acme"})
    assert me.json() == {"tenant": "acme", "roles": ["member"], "workspaces": ["w1"]}


async def test_a_caller_names_their_tenant_unless_they_have_one(
    client: httpx.AsyncClient, grants: Grants
) -> None:
    assert (await client.post("/checks", json=[], headers=AS_ROOT)).status_code == 400
    await grants.create_tenant("globex", owner=ALICE.id, by=ROOT)
    several = await client.post("/checks", json=[], headers=AS_ALICE)
    assert several.status_code == 400
    assert several.json() == {
        "detail": {"type": "tenant_required", "message": "name the tenant with X-Tenant"}
    }
    named = await client.post("/checks", json=[], headers={**AS_ALICE, "X-Tenant": "globex"})
    assert named.json() == []
    stranger = await client.post("/checks", json=[], headers={**AS_BOB, "X-Tenant": "acme"})
    assert stranger.status_code == 403


async def test_requests_are_bounded(client: httpx.AsyncClient) -> None:
    for params in ({"after_seq": -1}, {"limit": 0}, {"limit": 1001}):
        response = await client.get("/tenants/acme/audit", params=params, headers=AS_ALICE)
        assert response.status_code == 422
    question = {"action": "artifactr:open", "resource": WS}
    assert (
        await client.post("/checks", json=[question] * 100, headers=AS_ALICE)
    ).status_code == 200
    assert (
        await client.post("/checks", json=[question] * 101, headers=AS_ALICE)
    ).status_code == 422


async def test_a_groups_members_are_listed_in_order(client: httpx.AsyncClient) -> None:
    members = [{"kind": "user", "id": name} for name in ("carol", "bob")]
    for member in members:
        await client.post("/tenants/acme/members", json={"member": member}, headers=AS_ALICE)
    await client.put("/tenants/acme/groups/team", json={"members": members}, headers=AS_ALICE)
    groups = await client.get("/tenants/acme/groups", headers=AS_ALICE)
    assert groups.json() == {"team": members[::-1]}


async def test_an_owner_restricts_a_thread(client: httpx.AsyncClient) -> None:
    thread = {"kind": "thread", "workspace": "w1", "id": "t1"}
    restricted = await client.post(
        "/tenants/acme/restrictions", json={"on": thread}, headers=AS_ALICE
    )
    assert restricted.json()["event"] == {"type": "restricted", "on": thread}
    listed = await client.get(
        "/tenants/acme/restrictions", params={"workspace": "w1"}, headers=AS_ALICE
    )
    assert listed.json() == [thread]
    lifted = await client.post(
        "/tenants/acme/restrictions",
        json={"on": thread, "restricted": False},
        headers=AS_ALICE,
    )
    assert lifted.json()["event"]["type"] == "unrestricted"


async def test_a_principal_cant_take_the_libraries_actors_ids(client: httpx.AsyncClient) -> None:
    spoof = "reflexr:app:triage"
    member = {"member": {"kind": "service_principal", "id": spoof}}
    refusals = [
        await client.post("/tenants/acme/members", json=member, headers=AS_ALICE),
        await client.post("/tenants/acme/keys", json={"principal": spoof}, headers=AS_ALICE),
        await client.delete(f"/tenants/acme/members/service_principal/{spoof}", headers=AS_ALICE),
    ]
    assert [refused.status_code for refused in refusals] == [422, 422, 422]


async def test_the_audit_log_is_read_of_some_types_or_by_one_subject(
    client: httpx.AsyncClient,
) -> None:
    await client.post("/tenants/acme/members", json={"member": BOB}, headers=AS_ALICE)
    await client.put("/tenants/acme/groups/team", json={"members": [BOB]}, headers=AS_ALICE)
    typed = await client.get(
        "/tenants/acme/audit",
        params=[("type", "member_added"), ("type", "group_defined")],
        headers=AS_ALICE,
    )
    assert [e["event"]["type"] for e in typed.json()] == ["member_added", "group_defined"]
    tenant_by_root = await client.get(
        "/tenants/acme/audit", params={"actor_kind": "user", "actor": "root"}, headers=AS_ALICE
    )
    assert [e["event"]["type"] for e in tenant_by_root.json()] == ["tenant_created"]
    by_a_rule = await client.get(
        "/tenants/acme/audit",
        params={"actor_kind": "rule", "actor": "chat:x", "workspace": "notes"},
        headers=AS_ALICE,
    )
    assert by_a_rule.json() == []
    by_the_agent = await client.get(
        "/tenants/acme/audit", params={"actor_kind": "agent"}, headers=AS_ALICE
    )
    assert by_the_agent.json() == []
    assert (await client.put("/operators/carol", headers=AS_ROOT)).status_code == 200
    granted = await client.get("/audit", params={"type": "granted"}, headers=AS_ROOT)
    assert [(e["by"], e["event"]["grant"]["to"]) for e in granted.json()] == [
        (None, {"kind": "user", "id": "root"}),
        ({"kind": "user", "id": "root"}, {"kind": "user", "id": "carol"}),
    ]
    by_root = await client.get(
        "/audit", params={"actor_kind": "user", "actor": "root"}, headers=AS_ROOT
    )
    assert [e["event"]["type"] for e in by_root.json()] == [
        "deployment_tenant_created",
        "granted",
    ], "root created acme, and made carol an operator"


async def test_the_audit_log_reads_its_last_and_pages_back_from_an_entry(
    client: httpx.AsyncClient,
) -> None:
    await client.post("/tenants/acme/members", json={"member": BOB}, headers=AS_ALICE)
    await client.put("/tenants/acme/groups/team", json={"members": [BOB]}, headers=AS_ALICE)
    tail = await client.get("/tenants/acme/audit", params={"last": 2}, headers=AS_ALICE)
    assert [e["event"]["type"] for e in tail.json()] == ["member_added", "group_defined"]
    back = await client.get(
        "/tenants/acme/audit",
        params={"last": 2, "before_seq": tail.json()[0]["seq"]},
        headers=AS_ALICE,
    )
    assert [e["event"]["type"] for e in back.json()] == ["tenant_created"]
    window = await client.get(
        "/tenants/acme/audit",
        params={"last": 1, "after_seq": back.json()[0]["seq"], "before_seq": tail.json()[1]["seq"]},
        headers=AS_ALICE,
    )
    assert [e["event"]["type"] for e in window.json()] == ["member_added"]
    assert (await client.put("/operators/carol", headers=AS_ROOT)).status_code == 200
    deployment = await client.get("/audit", params={"last": 1}, headers=AS_ROOT)
    assert [e["event"]["grant"]["to"]["id"] for e in deployment.json()] == ["carol"]
    both = await client.get("/tenants/acme/audit", params={"limit": 1, "last": 1}, headers=AS_ALICE)
    assert both.status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {"type": "renamed"},
        {"actor": ""},
        {"actor": "bob"},
        {"workspace": "notes"},
        {"actor_kind": "user"},
        {"actor_kind": "user", "actor": "bob", "workspace": "notes"},
        {"actor_kind": "rule", "actor": "chat:x"},
        {"actor_kind": "agent", "actor": "bob"},
        {"actor_kind": "service_principal", "actor": "has:colon"},
        {"actor_kind": "group", "actor": "team"},
    ],
)
async def test_an_audit_filter_that_names_no_subject_is_refused(
    client: httpx.AsyncClient, params: dict[str, str]
) -> None:
    response = await client.get("/tenants/acme/audit", params=params, headers=AS_ALICE)
    assert response.status_code == 422, params


async def test_anyone_signed_in_reads_the_catalog(client: httpx.AsyncClient) -> None:
    catalog = (await client.get("/catalog", headers=AS_BOB)).json()
    roles = {role["name"]: role["kinds"] for role in catalog["roles"]}
    assert list(roles) == ["admin", "owner", "editor", "viewer"], "where each is granted, in order"
    assert roles["viewer"] == ["workspace", "thread", "artifact", "rule"]
    assert not {"operator", "application", "member", "rule"} & roles.keys()
    assert "artifactr:open" in catalog["custom_actions"]
    assert catalog["custom_kinds"] == ["workspace", "thread", "artifact", "rule"]
    assert (await client.get("/catalog")).status_code == 401


async def test_admins_switch_integrations_and_members_read_them(client: httpx.AsyncClient) -> None:
    await client.post("/tenants/acme/members", json={"member": BOB}, headers=AS_ALICE)
    viewer = {"role": "viewer", "on": {"kind": "workspace", "workspace": "team/notes"}, "to": BOB}
    await client.post("/tenants/acme/grants", json=viewer, headers=AS_ALICE)

    off = await client.put(
        "/tenants/acme/integrations/excalidraw", json={"on": False}, headers=AS_ALICE
    )
    assert off.status_code == 200
    assert off.json()["tenant"] == {
        "on": False,
        "by": ALICE.model_dump(),
        "at": off.json()["tenant"]["at"],
    }
    assert off.json()["enabled"] is False
    on = await client.put(
        "/tenants/acme/integrations/ui%3Amini-apps",
        json={"on": True, "workspace": "team/notes"},
        headers=AS_ALICE,
    )
    assert (on.json()["key"], on.json()["enabled"]) == ("ui:mini-apps", True)
    unset = await client.put(
        "/tenants/acme/integrations/excalidraw", json={"on": None}, headers=AS_ALICE
    )
    assert (unset.json()["tenant"], unset.json()["enabled"]) == (None, True)

    listed = await client.get("/tenants/acme/integrations", headers=AS_ALICE)
    assert [state["key"] for state in listed.json()][:2] == ["tracker:plane", "tracker:vikunja"]
    in_notes = await client.get(
        "/tenants/acme/integrations", params={"workspace": "team/notes"}, headers=AS_ALICE
    )
    [mini_apps] = [state for state in in_notes.json() if state["key"] == "ui:mini-apps"]
    assert mini_apps["workspace"]["on"] is True

    enabled = await client.get("/tenants/acme/workspaces/team/notes/integrations", headers=AS_BOB)
    assert enabled.status_code == 200
    assert enabled.json()["ui:mini-apps"] is True
    assert enabled.json()["excalidraw"] is True

    refused = await client.put(
        "/tenants/acme/integrations/ui:forms", json={"on": False}, headers=AS_BOB
    )
    assert refused.status_code == 403
    assert refused.json()["detail"]["message"] == (
        "grantr:manage_integrations on the tenant is refused"
    )
    elsewhere = await client.get("/tenants/acme/workspaces/w2/integrations", headers=AS_BOB)
    assert elsewhere.status_code == 403
    unknown = await client.put(
        "/tenants/acme/integrations/tracker:jira", json={"on": True}, headers=AS_ALICE
    )
    assert unknown.json()["detail"] == {
        "type": "invalid",
        "message": "there is no integration tracker:jira",
    }
    assert (
        await client.put("/tenants/acme/integrations/ui:forms", json={}, headers=AS_ALICE)
    ).status_code == 422, "on is required: null unsets it"

    audit = await client.get(
        "/tenants/acme/audit", params={"type": "integration_set"}, headers=AS_ALICE
    )
    assert [entry["event"] for entry in audit.json()] == [
        {"type": "integration_set", "workspace": None, "key": "excalidraw", "on": False},
        {"type": "integration_set", "workspace": "team/notes", "key": "ui:mini-apps", "on": True},
        {"type": "integration_set", "workspace": None, "key": "excalidraw", "on": None},
    ]
