"""The admin API, over HTTP: each command and list, /me, /checks, and the shapes of refusals."""

import httpx

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
    assert [e["event"]["type"] for e in audit] == ["granted", "granted", "revoked"]
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
