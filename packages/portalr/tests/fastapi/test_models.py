"""The models a person may choose for a turn: who may list them, and what is listed."""

import json
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import httpx
import pytest

from grantr.core import Resource, ServicePrincipal
from grantr.grants import Grants, InMemoryStorage
from portalr.actions import ACTIONS
from portalr.invites import Invite
from portalr.models import OfferedModel
from tests.fastapi.conftest import ALICE, BOB, CAROL, OPS, Stack, app_for

USE_MODEL = "artifactr:use_model"
BOOKKEEPING = ("artifactr:claim_thread", "artifactr:read_cursors", "artifactr:save_cursor")
AS = {name: {"X-User": name} for name in ("alice", "bob", "carol")}
ACME = {"X-Tenant": "acme"}
W1 = Resource(kind="workspace", workspace="w1")
OFFERED = [
    OfferedModel(id="default", label="Default"),
    OfferedModel(id="fast", label="Fast", family="openai"),
    OfferedModel(id="deep", label="Deep", family="anthropic", reasoning=True),
    OfferedModel(id="here", label="On this machine", family="local", local=True),
]


class Allowed:
    """The workspace's ``models:allowed``, as the application reads it, and who asked."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, str]] = []

    async def __call__(self, tenant: str, workspace: str) -> Sequence[OfferedModel]:
        self.asked.append((tenant, workspace))
        return OFFERED[:3] if workspace == "w1" else OFFERED[:2]


@pytest.fixture
async def choosing() -> Grants:
    """grantr with artifactr's ``use_model`` beside portalr's catalog: acme's owner holds it."""
    grants = Grants(InMemoryStorage(), catalogs=[ACTIONS, [USE_MODEL, *BOOKKEEPING]])
    await grants.first_operator(OPS.id)
    await grants.create_tenant("acme", owner=ALICE.id, by=OPS)
    await grants.create_tenant("globex", owner=CAROL.id, by=OPS)
    await grants.add_member("acme", BOB, by=ALICE)
    return grants


@pytest.fixture
def allowed() -> Allowed:
    return Allowed()


@pytest.fixture
async def models_client(
    choosing: Grants, stack: Stack, invite: Invite, ui: Path, allowed: Allowed
) -> AsyncIterator[httpx.AsyncClient]:
    app = app_for(choosing, stack.readers(), invite, ui, models=allowed)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app/portalr"
    ) as client:
        yield client


async def listed(
    client: httpx.AsyncClient, workspace: str, headers: dict[str, str]
) -> httpx.Response:
    return await client.get("/v1/models", params={"workspace": workspace}, headers=headers)


async def test_a_person_who_may_choose_sees_the_workspaces_models(
    models_client: httpx.AsyncClient, allowed: Allowed
) -> None:
    answer = await listed(models_client, "w1", {**AS["alice"], **ACME})
    assert answer.status_code == 200
    assert answer.headers["cache-control"] == "no-store"
    assert answer.json() == {
        "models": [
            {"id": "default", "label": "Default", "family": "", "local": False, "reasoning": False},
            {"id": "fast", "label": "Fast", "family": "openai", "local": False, "reasoning": False},
            {
                "id": "deep",
                "label": "Deep",
                "family": "anthropic",
                "local": False,
                "reasoning": True,
            },
        ]
    }
    assert allowed.asked == [("acme", "w1")]
    other = await listed(models_client, "w2", {**AS["alice"], **ACME})
    assert [model["id"] for model in other.json()["models"]] == ["default", "fast"]


async def test_the_answer_names_no_gateway_and_no_key(models_client: httpx.AsyncClient) -> None:
    answer = (await listed(models_client, "w1", {**AS["alice"], **ACME})).json()
    assert set(answer) == {"models"}
    fields = {"id", "label", "family", "local", "reasoning"}
    assert all(set(model) == fields for model in answer["models"])
    assert "http" not in json.dumps(answer)


async def test_a_member_without_use_model_is_refused_before_the_list_is_read(
    models_client: httpx.AsyncClient, allowed: Allowed
) -> None:
    refused = await listed(models_client, "w1", {**AS["bob"], **ACME})
    assert refused.status_code == 403
    assert refused.json()["detail"]["type"] == "forbidden"
    assert allowed.asked == []


async def test_a_caller_outside_the_tenant_is_refused(
    models_client: httpx.AsyncClient, allowed: Allowed
) -> None:
    refused = await listed(models_client, "w1", {**AS["carol"], **ACME})
    assert refused.status_code == 403
    assert allowed.asked == []


async def test_the_tenant_is_named_or_the_keys_own(
    models_client: httpx.AsyncClient, choosing: Grants, allowed: Allowed
) -> None:
    unnamed = await listed(models_client, "w1", AS["alice"])
    assert unnamed.status_code == 400
    assert unnamed.json()["detail"]["type"] == "tenant_required"
    other = await listed(models_client, "w1", {**AS["alice"], **ACME, "X-Key-Tenant": "globex"})
    assert other.status_code == 403
    assert other.json()["detail"]["message"] == "this caller's key is for another tenant"
    bot = ServicePrincipal(id="bot")
    await choosing.add_member("acme", bot, by=ALICE)
    await choosing.grant("acme", "editor", on=W1, to=bot, by=ALICE)
    keyed = {"X-Principal": "bot", "X-Key-Tenant": "acme"}
    assert (await listed(models_client, "w1", keyed)).status_code == 200
    assert allowed.asked == [("acme", "w1")]


async def test_a_workspace_id_is_an_id(models_client: httpx.AsyncClient) -> None:
    bad = await listed(models_client, "../w1", {**AS["alice"], **ACME})
    assert bad.status_code == 422
    missing = await models_client.get("/v1/models", headers={**AS["alice"], **ACME})
    assert missing.status_code == 422


async def test_without_the_hook_there_is_no_route(client: httpx.AsyncClient) -> None:
    answer = await client.get("/v1/models", params={"workspace": "w1"}, headers=AS["alice"])
    assert answer.status_code == 404


async def test_without_a_caller_it_is_unauthorized(models_client: httpx.AsyncClient) -> None:
    answer = await listed(models_client, "w1", ACME)
    assert answer.status_code == 401
