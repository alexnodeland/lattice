"""Connections over the admin API (grantr ADR-0043): a member lists and revokes their own, and the
tenant's admins every one."""

import httpx

from grantr.core import ClientInfo, User
from grantr.grants import Grants
from tests.fastapi.conftest import ALICE

AS_ALICE = {"X-User": "alice"}
AS_BOB = {"X-User": "bob"}
CLAUDE = ClientInfo(client_id="client_claude", name="Claude")


async def test_a_member_lists_and_revokes_their_own(
    grants: Grants, client: httpx.AsyncClient
) -> None:
    bob = User(id="bob")
    await grants.add_member("acme", bob, by=ALICE)
    bobs = await grants.connections().connect("acme", CLAUDE, toolsets=["files"], by=bob)
    alices = await grants.connections().connect("acme", CLAUDE, by=ALICE)
    [listed] = (await client.get("/tenants/acme/connections", headers=AS_BOB)).json()
    assert (listed["id"], listed["client"]["name"], sorted(listed["toolsets"])) == (
        bobs.id,
        "Claude",
        ["core", "files"],
    )
    everyone = await client.get("/tenants/acme/connections", headers=AS_ALICE)
    assert [c["id"] for c in everyone.json()] == [bobs.id, alices.id]
    only = await client.get("/tenants/acme/connections", params={"user": "bob"}, headers=AS_ALICE)
    assert [c["id"] for c in only.json()] == [bobs.id]
    others = await client.get("/tenants/acme/connections", params={"user": "alice"}, headers=AS_BOB)
    assert (others.status_code, others.json()["detail"]["type"]) == (403, "forbidden")
    refused = await client.delete(f"/tenants/acme/connections/{alices.id}", headers=AS_BOB)
    assert refused.status_code == 403
    revoked = await client.delete(f"/tenants/acme/connections/{bobs.id}", headers=AS_BOB)
    assert revoked.json()["event"]["type"] == "connection_revoked"
    again = await client.delete(f"/tenants/acme/connections/{bobs.id}", headers=AS_BOB)
    assert (again.status_code, again.json()["detail"]["type"]) == (422, "invalid")
    by_admin = await client.delete(f"/tenants/acme/connections/{alices.id}", headers=AS_ALICE)
    assert by_admin.status_code == 200
