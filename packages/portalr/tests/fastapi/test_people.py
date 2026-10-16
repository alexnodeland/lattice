"""Naming people by email: who may see whose, and what is left out."""

import logging
from collections.abc import Collection
from pathlib import Path

import httpx
import pytest

from grantr.grants import Grants
from portalr.invites import Invite
from tests.fastapi.conftest import Directory, Stack, app_for

AS = {name: {"X-User": name} for name in ("alice", "bob", "carol", "ops")}
ACME = {"X-Tenant": "acme"}


async def names(
    client: httpx.AsyncClient, ids: list[str], headers: dict[str, str]
) -> httpx.Response:
    return await client.get("/v1/people", params=[("id", each) for each in ids], headers=headers)


async def test_a_member_sees_the_emails_of_the_tenants_members(
    naming_client: httpx.AsyncClient, directory: Directory
) -> None:
    answer = await names(naming_client, ["alice", "bob"], {**AS["bob"], **ACME})
    assert answer.status_code == 200
    assert answer.json() == {"people": {"alice": "alice@acme.test", "bob": "bob@acme.test"}}
    assert answer.headers["cache-control"] == "no-store"
    assert directory.asked == [["alice", "bob"]]


async def test_an_id_that_is_not_a_member_is_left_out_and_never_asked_after(
    naming_client: httpx.AsyncClient, directory: Directory
) -> None:
    answer = await names(naming_client, ["carol", "ops", "nobody", "alice"], {**AS["bob"], **ACME})
    assert answer.json() == {"people": {"alice": "alice@acme.test"}}
    assert directory.asked == [["alice"]], "Auth is asked only about members"
    only = await names(naming_client, ["carol", "nobody"], {**AS["bob"], **ACME})
    assert only.json() == {"people": {}}
    assert directory.asked == [["alice"]], "and not at all where none is"


async def test_unknown_and_not_allowed_and_without_an_email_look_alike(
    naming_client: httpx.AsyncClient,
) -> None:
    headers = {**AS["alice"], **ACME}
    answers = [
        (await names(naming_client, [each], headers)).json()
        for each in ("carol", "nobody", "bob_is_not_here")
    ]
    assert answers == [{"people": {}}] * 3
    assert (await names(naming_client, ["alice"], headers)).json() == {
        "people": {"alice": "alice@acme.test"}
    }


async def test_a_caller_outside_the_tenant_sees_no_one(
    naming_client: httpx.AsyncClient, directory: Directory
) -> None:
    refused = await names(naming_client, ["alice"], {**AS["carol"], **ACME})
    assert refused.status_code == 403
    assert refused.json()["detail"]["type"] == "forbidden"
    missing = await names(naming_client, ["alice"], {**AS["carol"], "X-Tenant": "no-such-tenant"})
    assert (missing.status_code, missing.json()) == (403, refused.json()), "a tenant that isn't"
    assert directory.asked == []


async def test_without_a_tenant_only_an_operator_sees_people(
    naming_client: httpx.AsyncClient, directory: Directory
) -> None:
    assert (await names(naming_client, ["alice"], AS["alice"])).status_code == 403
    seen = await names(naming_client, ["alice", "carol", "ghost"], AS["ops"])
    assert seen.json() == {"people": {"alice": "alice@acme.test", "carol": "carol@globex.test"}}
    assert directory.asked == [["alice", "carol", "ghost"]]
    in_acme = await names(naming_client, ["carol"], {**AS["ops"], **ACME})
    assert in_acme.json() == {"people": {"carol": "carol@globex.test"}}, (
        "an operator, in any tenant"
    )


async def test_a_key_sees_no_one(naming_client: httpx.AsyncClient, directory: Directory) -> None:
    key = {"X-Principal": "ci", "X-Key-Tenant": "acme", **ACME}
    refused = await names(naming_client, ["alice"], key)
    assert refused.status_code == 403
    assert directory.asked == []


async def test_a_key_for_another_tenant_sees_no_one(naming_client: httpx.AsyncClient) -> None:
    other = {**AS["alice"], "X-Key-Tenant": "globex", **ACME}
    assert (await names(naming_client, ["alice"], other)).status_code == 403


@pytest.mark.parametrize("count", [0, 101])
async def test_one_to_a_hundred_ids_are_asked_after(
    naming_client: httpx.AsyncClient, count: int
) -> None:
    ids = [f"u{i}" for i in range(count)]
    answer = await names(naming_client, ids, {**AS["alice"], **ACME})
    assert answer.status_code == 422
    assert answer.json()["detail"][0]["loc"] == ["query", "id"]


async def test_a_hundred_ids_are_answered(naming_client: httpx.AsyncClient) -> None:
    ids = ["alice", *(f"u{i}" for i in range(99))]
    answer = await names(naming_client, ids, {**AS["alice"], **ACME})
    assert answer.json() == {"people": {"alice": "alice@acme.test"}}


async def test_a_caller_with_no_name_is_refused(naming_client: httpx.AsyncClient) -> None:
    assert (await names(naming_client, ["alice"], ACME)).status_code == 401


async def test_a_hook_that_finds_no_one_is_not_an_error(
    grants: Grants, stack: Stack, invite: Invite, ui: Path
) -> None:
    async def nobody(ids: Collection[str]) -> dict[str, str]:
        return {}

    app = app_for(grants, stack.readers(), invite, ui, nobody)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://app/portalr") as client:
        answer = await names(client, ["alice"], {**AS["alice"], **ACME})
    assert (answer.status_code, answer.json()) == (200, {"people": {}})


async def test_no_email_reaches_a_log(
    naming_client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        await names(naming_client, ["alice", "bob"], {**AS["bob"], **ACME})
        await names(naming_client, ["alice"], {**AS["carol"], **ACME})
    assert "@acme.test" not in caplog.text


async def test_there_is_no_route_without_a_hook_and_config_says_so(
    client: httpx.AsyncClient, naming_client: httpx.AsyncClient
) -> None:
    assert (await names(client, ["alice"], {**AS["alice"], **ACME})).status_code == 404
    assert (await client.get("/config.json")).json()["people"] is False
    assert (await naming_client.get("/config.json")).json()["people"] is True
