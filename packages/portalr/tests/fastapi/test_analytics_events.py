"""The server's own events: an invitation is recorded in the inviter's tenant, after it is made."""

import json
from pathlib import Path

import httpx

from grantr.grants import Grants
from portalr.invites import Invite
from portalr.readers import Analytics, Readers
from portalr.readers.analytics import distinct_id

from .conftest import app_for

KEY = b"the deployment's key"


async def test_an_invitation_is_recorded_in_the_tenant_by_its_inviter(
    grants: Grants, invite: Invite, ui: Path
) -> None:
    rows: list[dict[str, object]] = []

    def clickhouse(request: httpx.Request) -> httpx.Response:
        rows.append(json.loads(request.content))
        return httpx.Response(200)

    writer = httpx.AsyncClient(transport=httpx.MockTransport(clickhouse))
    analytics = Analytics("http://clickhouse:8123", KEY, writer=writer)
    app = app_for(grants, Readers(analytics=analytics), invite, ui)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app/portalr"
    ) as client:
        response = await client.post(
            "/v1/invites",
            json={"email": "dan@acme.com"},
            headers={"x-user": "alice", "x-tenant": "acme"},
        )
    assert response.status_code == 201
    (row,) = rows
    assert row["tenant_id"] == "acme"
    assert row["event"] == "member.invited.v1"
    assert row["distinct_id"] == distinct_id(KEY, "alice")
    assert row["props"] == {"outcome": "invited"}
    assert "dan" not in json.dumps(row)


async def test_a_refused_invitation_records_nothing(
    grants: Grants, invite: Invite, ui: Path
) -> None:
    rows: list[bytes] = []

    def clickhouse(request: httpx.Request) -> httpx.Response:
        rows.append(request.content)
        return httpx.Response(200)

    writer = httpx.AsyncClient(transport=httpx.MockTransport(clickhouse))
    analytics = Analytics("http://clickhouse:8123", KEY, writer=writer)
    app = app_for(grants, Readers(analytics=analytics), invite, ui)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app/portalr"
    ) as client:
        response = await client.post(
            "/v1/invites",
            json={"email": "eve@x.com"},
            headers={"x-user": "carol", "x-tenant": "acme"},
        )
    assert response.status_code == 403
    assert rows == []


async def test_a_tenants_adoption_is_read_as_that_tenant(
    grants: Grants, invite: Invite, ui: Path
) -> None:
    tenants: list[str] = []

    def clickhouse(request: httpx.Request) -> httpx.Response:
        tenants.append(request.url.params["param_tenant"])
        return httpx.Response(200, text="")

    reader = httpx.AsyncClient(transport=httpx.MockTransport(clickhouse))
    analytics = Analytics("http://clickhouse:8123", KEY, reader=reader)
    app = app_for(grants, Readers(analytics=analytics), invite, ui)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app/portalr"
    ) as client:
        response = await client.get(
            "/v1/adoption",
            params={"start": "2026-10-01T00:00:00Z", "end": "2026-10-22T00:00:00Z"},
            headers={"x-user": "alice", "x-tenant": "acme"},
        )
    assert response.json()["status"] == "ok"
    assert response.json()["data"]["complete"] is True
    assert set(tenants) == {"acme"}
