"""Naming people by email: who may see whose, and what is left out."""

import logging
from collections.abc import AsyncIterator, Collection
from pathlib import Path

import httpx
import pytest

from grantr.core import User
from grantr.grants import Grants
from portalr.invites import Invite
from portalr.people import SupabasePeople
from tests.fastapi.conftest import EMAILS, Directory, Stack, app_for

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


@pytest.fixture
def supabase() -> list[httpx.Request]:
    """The requests the real hook sent to Supabase Auth."""
    return []


@pytest.fixture
async def real_client(
    grants: Grants, stack: Stack, invite: Invite, ui: Path, supabase: list[httpx.Request]
) -> AsyncIterator[httpx.AsyncClient]:
    """The application with the real ``SupabasePeople``, over a Supabase Auth that answers
    from ``EMAILS``, 500 for ``flaky`` and 404 for anyone else."""

    def auth(request: httpx.Request) -> httpx.Response:
        supabase.append(request)
        user = request.url.path.removeprefix("/auth/v1/admin/users/")
        if user == "flaky":
            return httpx.Response(500, json={"msg": "boom"})
        if user in EMAILS:
            return httpx.Response(200, json={"id": user, "email": EMAILS[user]})
        return httpx.Response(404, json={})

    hook = SupabasePeople(
        "https://project.supabase.co",
        "sb_secret_x",
        httpx.AsyncClient(transport=httpx.MockTransport(auth)),
    )
    app = app_for(grants, stack.readers(), invite, ui, hook)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app/portalr"
    ) as client:
        yield client


async def test_no_email_reaches_a_log(
    real_client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Over the real hook, with httpx logging every request, the failing one included."""
    with caplog.at_level(logging.DEBUG):
        seen = await names(real_client, ["alice", "bob"], {**AS["bob"], **ACME})
        await names(real_client, ["alice"], {**AS["carol"], **ACME})
        await names(real_client, ["flaky"], AS["ops"])
    assert seen.json()["people"]["alice"] == "alice@acme.test"
    assert "@" not in caplog.text.replace("sb_secret_x", ""), "no email, and no address"
    assert "/auth/v1/admin/users/alice" in caplog.text, "the ids are what is logged"
    assert "/auth/v1/admin/users/flaky" in caplog.text, "the failing read too"


async def test_a_cached_email_is_not_given_to_a_later_caller_who_may_not_see_it(
    real_client: httpx.AsyncClient, supabase: list[httpx.Request]
) -> None:
    first = await names(real_client, ["alice"], {**AS["bob"], **ACME})
    assert first.json() == {"people": {"alice": "alice@acme.test"}}
    assert len(supabase) == 1
    # carol, in globex, asks after alice, who is in acme only: the cache holds her email.
    later = await names(real_client, ["alice"], {**AS["carol"], "X-Tenant": "globex"})
    assert later.json() == {"people": {}}
    outsider = await names(real_client, ["alice"], {**AS["carol"], **ACME})
    assert outsider.status_code == 403
    assert len(supabase) == 1, "and Supabase was asked once, for the one who may"


async def test_a_user_in_two_tenants_sees_the_members_of_the_one_they_name(
    grants: Grants, naming_client: httpx.AsyncClient, directory: Directory
) -> None:
    await grants.add_member("globex", User(id="alice"), by=User(id="carol"))
    from_acme = await names(naming_client, ["alice", "bob", "carol"], {**AS["alice"], **ACME})
    assert from_acme.json() == {"people": {"alice": "alice@acme.test", "bob": "bob@acme.test"}}
    from_globex = await names(
        naming_client, ["alice", "bob", "carol"], {**AS["alice"], "X-Tenant": "globex"}
    )
    assert from_globex.json() == {
        "people": {"alice": "alice@acme.test", "carol": "carol@globex.test"}
    }
    assert directory.asked == [["alice", "bob"], ["alice", "carol"]]


async def test_an_operator_who_is_a_member_of_the_tenant_sees_everyone(
    grants: Grants, naming_client: httpx.AsyncClient
) -> None:
    await grants.add_member("acme", User(id="ops"), by=User(id="alice"))
    seen = await names(naming_client, ["carol", "bob", "ops"], {**AS["ops"], **ACME})
    assert seen.json() == {
        "people": {
            "carol": "carol@globex.test",
            "bob": "bob@acme.test",
            "ops": "ops@deployment.test",
        }
    }, "a former member, an outsider and themselves"


@pytest.mark.parametrize("tenant", ["a~b", ""])
async def test_a_malformed_tenant_is_a_422(naming_client: httpx.AsyncClient, tenant: str) -> None:
    answer = await names(naming_client, ["alice"], {**AS["alice"], "X-Tenant": tenant})
    assert answer.status_code == 422
    assert answer.json()["detail"][0]["loc"] == ["header", "X-Tenant"]


async def test_a_hook_that_answers_more_than_was_asked_is_not_believed(
    grants: Grants, stack: Stack, invite: Invite, ui: Path
) -> None:
    async def everyone(ids: Collection[str]) -> dict[str, str]:
        return {**dict.fromkeys(ids, ""), "carol": "carol@globex.test", "alice": "alice@acme.test"}

    app = app_for(grants, stack.readers(), invite, ui, everyone)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://app/portalr") as client:
        answer = await names(client, ["bob", "alice"], {**AS["bob"], **ACME})
    assert answer.json() == {"people": {"alice": "alice@acme.test"}}, "no carol, no empty email"


async def test_there_is_no_route_without_a_hook_and_config_says_so(
    client: httpx.AsyncClient, naming_client: httpx.AsyncClient
) -> None:
    assert (await names(client, ["alice"], {**AS["alice"], **ACME})).status_code == 404
    assert (await client.get("/config.json")).json()["people"] is False
    assert (await naming_client.get("/config.json")).json()["people"] is True
