"""Bindings over the admin API (grantr ADR-0041): a tenant's owners and admins list, bind and
unbind its sources' connections, and the operator's bindings are read only."""

import httpx

from grantr.core import User
from grantr.grants import Grants
from tests.fastapi.conftest import ALICE

AS_ALICE = {"X-User": "alice"}
AS_BOB = {"X-User": "bob"}
FORGE = {"workspace": "w1", "source": "forge", "connection": "inst_1"}


async def test_an_owner_binds_lists_and_unbinds(client: httpx.AsyncClient) -> None:
    body = FORGE | {
        "select": {"repository": "acme/api"},
        "types": ["forge:issue"],
        "trust": "untrusted",
    }
    bound = await client.post("/tenants/acme/bindings", json=body, headers=AS_ALICE)
    assert bound.status_code == 201
    event = bound.json()["event"]
    assert (event["type"], event["types"], event["trust"]) == (
        "binding_added",
        ["forge:issue"],
        "untrusted",
    )
    [listed] = (await client.get("/tenants/acme/bindings", headers=AS_ALICE)).json()
    assert (listed["id"], listed["select"], listed["by"]) == (
        event["binding"],
        {"repository": "acme/api"},
        "user:alice",
    )
    elsewhere = await client.get(
        "/tenants/acme/bindings", params={"workspace": "w2"}, headers=AS_ALICE
    )
    assert elsewhere.json() == []
    gone = await client.delete(f"/tenants/acme/bindings/{event['binding']}", headers=AS_ALICE)
    assert gone.json()["event"]["type"] == "binding_removed"
    assert (await client.get("/tenants/acme/bindings", headers=AS_ALICE)).json() == []


async def test_a_binding_is_refused_to_a_member_and_when_malformed(
    grants: Grants, client: httpx.AsyncClient
) -> None:
    await grants.add_member("acme", User(id="bob"), by=ALICE)
    refused = await client.post("/tenants/acme/bindings", json=FORGE, headers=AS_BOB)
    assert (refused.status_code, refused.json()["detail"]["type"]) == (403, "forbidden")
    assert (await client.get("/tenants/acme/bindings", headers=AS_BOB)).status_code == 403
    malformed = await client.post(
        "/tenants/acme/bindings", json=FORGE | {"source": "Forge"}, headers=AS_ALICE
    )
    assert (malformed.status_code, malformed.json()["detail"]["type"]) == (422, "invalid")
    untrusting = await client.post(
        "/tenants/acme/bindings", json=FORGE | {"trust": "trusted"}, headers=AS_ALICE
    )
    assert untrusting.status_code == 422
    unknown = await client.delete("/tenants/acme/bindings/bnd_" + "0" * 16, headers=AS_ALICE)
    assert unknown.status_code == 422
