"""Approvals over the admin API (grantr ADR-0040): those a person may answer, each one as it
stands, and the first answer, a caller's own confirmation on portalr's confirm page alone."""

from datetime import UTC, datetime, timedelta
from typing import Any, get_args

import httpx
import pytest

from grantr.core import Resource, User
from grantr.fastapi.router import AnswerGiven, ApprovalAnswer, ApprovalAnswerer, ApprovalView
from grantr.grants import Grants
from lattice_core.approvals import (
    CONFIRM_SURFACE,
    Answered,
    Answerers,
    Approval,
    ApprovalRequest,
    Rendering,
    Subject,
    arguments_digest,
)
from lattice_core.capabilities import Caller, JsonObject, PersonCaller, RunCaller, Scope
from tests.fastapi.conftest import ALICE, ROOT

AS_BOB = {"X-User": "bob"}
AS_CAROL = {"X-User": "carol"}
AS_ERIN = {"X-User": "erin"}
ARGUMENTS: JsonObject = {"artifact": "a1", "text": "hello"}
DIGEST = arguments_digest(ARGUMENTS)
RUN = RunCaller(id="run_1", agent="helper", on_behalf_of="carol")


@pytest.fixture(autouse=True)
async def members(grants: Grants) -> None:
    """bob is w1's admin, who answers; carol its editor, whom the run is for; erin a member."""
    for user in ("bob", "carol", "erin"):
        await grants.add_member("acme", User(id=user), by=ALICE)
    w1 = Resource(kind="workspace", workspace="w1")
    await grants.grant("acme", "admin", on=w1, to=User(id="bob"), by=ALICE)
    await grants.grant("acme", "editor", on=w1, to=User(id="carol"), by=ALICE)


async def _ask(
    grants: Grants,
    answerers: Answerers | None = None,
    *,
    tenant: str = "acme",
    workspace: str = "w1",
    asked_by: Caller = RUN,
) -> Approval:
    return await grants.approvals().ask(
        ApprovalRequest(
            scope=Scope(tenant_id=tenant, workspace_id=workspace),
            capability="artifactr.edit_text",
            version="1.0.0",
            rendering=Rendering(title="Edit a1", arguments=ARGUMENTS),
            arguments_digest=DIGEST,
            asked_by=asked_by,
            answerers=answerers or Answerers(action="grantr:answer_approval"),
            deadline=datetime.now(UTC) + timedelta(hours=1),
        )
    )


def _json(approval: Approval) -> dict[str, Any]:
    return approval.model_dump(mode="json")


def _answer(*, approved: bool = True, **changes: Any) -> dict[str, Any]:
    return {"approved": approved, "arguments_digest": DIGEST} | changes


async def test_a_person_lists_what_they_may_answer(
    grants: Grants, client: httpx.AsyncClient
) -> None:
    in_w1 = await _ask(grants)
    await _ask(grants, workspace="w2")
    listed = await client.get("/tenants/acme/approvals", headers=AS_BOB)
    assert listed.json() == [_json(in_w1)], "in every workspace they may answer in"
    narrowed = await client.get(
        "/tenants/acme/approvals", params={"workspace": "w2"}, headers=AS_BOB
    )
    assert narrowed.json() == []
    assert (await client.get("/tenants/acme/approvals", headers=AS_CAROL)).json() == []
    stranger = await client.get("/tenants/acme/approvals", headers={"X-User": "dave"})
    assert (stranger.status_code, stranger.json()["detail"]["type"]) == (403, "forbidden")


async def test_an_approval_is_read_by_its_answerers_and_the_person_it_was_for(
    grants: Grants, client: httpx.AsyncClient
) -> None:
    asked = await _ask(grants)
    for who in (AS_BOB, AS_CAROL):
        read = await client.get(f"/tenants/acme/approvals/{asked.id}", headers=who)
        assert read.json() == _json(asked)
    for path in (f"/tenants/acme/approvals/{asked.id}", "/tenants/acme/approvals/apr~acme~x"):
        hidden = await client.get(path, headers=AS_ERIN)
        assert (hidden.status_code, hidden.json()["detail"]["type"]) == (404, "not_found")


async def test_an_approval_is_read_only_under_its_own_tenant(
    grants: Grants, client: httpx.AsyncClient
) -> None:
    await grants.create_tenant("globex", owner=ALICE.id, by=ROOT)
    asked = await _ask(grants)
    elsewhere = await client.get(
        f"/tenants/globex/approvals/{asked.id}", headers={"X-User": "alice"}
    )
    assert elsewhere.status_code == 404, "alice may answer it, but in acme"


async def test_the_first_answer_wins_and_the_approval_shows_it(
    grants: Grants, client: httpx.AsyncClient
) -> None:
    asked = await _ask(grants)
    path = f"/tenants/acme/approvals/{asked.id}/answer"
    answered = await client.post(path, json=_answer(reason="fine"), headers=AS_BOB)
    assert answered.status_code == 200
    body = answered.json()
    assert (body["state"], body["answer"]["by"], body["answer"]["surface"]) == (
        "approved",
        {"id": "bob", "service": False, "groups": []},
        "portalr",
    )
    assert body["answer"]["reason"] == "fine"
    again = await client.post(path, json=_answer(approved=False), headers=AS_BOB)
    assert (again.status_code, again.json()["detail"]["type"]) == (409, "invalid_state")
    assert "approved by bob on portalr" in again.json()["detail"]["message"]
    shown = await client.get(f"/tenants/acme/approvals/{asked.id}", headers=AS_CAROL)
    assert shown.json()["state"] == "approved", "the first answer, on every surface"


async def test_an_answer_is_refused_to_who_may_not_give_it_or_to_other_arguments(
    grants: Grants, client: httpx.AsyncClient
) -> None:
    asked = await _ask(grants)
    path = f"/tenants/acme/approvals/{asked.id}/answer"
    sees = await client.post(path, json=_answer(), headers=AS_CAROL)
    assert (sees.status_code, sees.json()["detail"]["type"]) == (403, "forbidden")
    unseen = await client.post(path, json=_answer(), headers=AS_ERIN)
    assert unseen.status_code == 404
    other = await client.post(path, json=_answer(arguments_digest="0" * 64), headers=AS_BOB)
    assert (other.status_code, other.json()["detail"]["type"]) == (409, "version_conflict")
    for malformed in (_answer(arguments_digest="abc"), _answer(surface="mcp")):
        assert (await client.post(path, json=malformed, headers=AS_BOB)).status_code == 422
    assert (await grants.approvals().get(asked.id)).state == "pending"


async def test_a_confirmation_is_its_callers_alone_on_the_confirm_page(
    grants: Grants, client: httpx.AsyncClient
) -> None:
    caller = Answerers(subjects=frozenset({"carol"}), confirmation=True)
    asked = await _ask(grants, caller, asked_by=PersonCaller(id="carol"))
    path = f"/tenants/acme/approvals/{asked.id}/answer"
    hidden = await client.post(path, json=_answer(surface=CONFIRM_SURFACE), headers=AS_BOB)
    assert hidden.status_code == 404, "bob holds the action, but it is carol's confirmation"
    elsewhere = await client.post(path, json=_answer(), headers=AS_CAROL)
    assert (elsewhere.status_code, elsewhere.json()["detail"]["type"]) == (403, "forbidden")
    confirmed = await client.post(path, json=_answer(surface=CONFIRM_SURFACE), headers=AS_CAROL)
    assert confirmed.json()["answer"]["surface"] == CONFIRM_SURFACE


def test_the_surfaces_an_answer_names_are_portalrs_pages() -> None:
    assert get_args(ApprovalAnswer.model_fields["surface"].annotation) == (
        "portalr",
        CONFIRM_SURFACE,
    )


def test_an_approval_is_shown_with_every_field_lattice_core_gives_it() -> None:
    assert ApprovalView.model_fields.keys() == Approval.model_fields.keys()
    assert AnswerGiven.model_fields.keys() == Answered.model_fields.keys()
    assert ApprovalAnswerer.model_fields.keys() == Subject.model_fields.keys()
