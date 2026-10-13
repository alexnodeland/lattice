"""The test application's restricted threads: hidden from the workspace, and shared by a grant.

The app restricts and shares a thread from its menu (portalr ADR-0022); this holds the test
application to what the scenarios rely on: a restricted thread is missing from an editor's reads,
and grantr's check that they may read it turns false; a viewer's grant on it shows it again, read
only; revoking it hides it again, and lifting the restriction shows it to the workspace; and an
editor may neither restrict one nor list who holds a role.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.app.main import create_app

THREADS = "/artifactr/v1/workspaces/notes"
GRANTS = "/grantr/v1/tenants/acme"
THREAD = {"kind": "thread", "workspace": "notes", "id": "thr_shared"}
BOB_VIEWS = {"role": "viewer", "on": THREAD, "to": {"kind": "user", "id": "bob"}}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), headers={"X-Tenant": "acme"}) as client:
        yield client


def command(client: TestClient, user: str, command: dict[str, Any]) -> Any:
    return client.post(
        f"{THREADS}/commands",
        headers={"x-user": user},
        json={"type": "command", "command_id": f"{user}-{command['type']}", "command": command},
    )


def as_alice(client: TestClient, path: str, body: dict[str, Any]) -> Any:
    return client.post(f"{GRANTS}/{path}", headers={"x-user": "alice"}, json=body)


def threads(client: TestClient, user: str) -> list[str]:
    listed = client.get(f"{THREADS}/threads", headers={"x-user": user}).json()
    return [thread["id"] for thread in listed]


def may_read(client: TestClient, user: str) -> bool:
    answers = client.post(
        "/grantr/v1/checks",
        headers={"x-user": user},
        json=[{"action": "artifactr:read_threads", "resource": THREAD}],
    ).json()
    return bool(answers[0])


@pytest.fixture
def restricted(client: TestClient) -> TestClient:
    """alice's thread, restricted."""
    created = command(client, "alice", {"type": "create_thread", "thread_id": "thr_shared"})
    assert created.status_code == 200
    assert as_alice(client, "restrictions", {"on": THREAD}).status_code == 200
    return client


def test_a_restricted_thread_is_hidden_and_grantrs_check_turns_false(
    restricted: TestClient,
) -> None:
    assert "thr_shared" not in threads(restricted, "bob")
    assert not may_read(restricted, "bob")
    assert may_read(restricted, "alice")


def test_a_viewers_grant_shows_it_read_only_and_revoking_hides_it_again(
    restricted: TestClient,
) -> None:
    assert as_alice(restricted, "grants", BOB_VIEWS).status_code == 201
    assert "thr_shared" in threads(restricted, "bob")
    assert may_read(restricted, "bob")
    posted = command(
        restricted, "bob", {"type": "post_message", "thread_id": "thr_shared", "content": "hi"}
    )
    assert posted.status_code == 403

    assert as_alice(restricted, "revocations", BOB_VIEWS).status_code == 200
    assert "thr_shared" not in threads(restricted, "bob")


def test_lifting_the_restriction_shows_it_to_the_workspace(restricted: TestClient) -> None:
    lifted = as_alice(restricted, "restrictions", {"on": THREAD, "restricted": False})
    assert lifted.status_code == 200
    assert "thr_shared" in threads(restricted, "bob")


def test_an_editor_may_not_restrict_a_thread_or_list_its_grants(client: TestClient) -> None:
    created = command(client, "bob", {"type": "create_thread", "thread_id": "thr_shared"})
    assert created.status_code == 200
    refused = client.post(f"{GRANTS}/restrictions", headers={"x-user": "bob"}, json={"on": THREAD})
    assert refused.status_code == 403
    assert "grantr:restrict" in refused.json()["detail"]["message"]
    listed = client.get(
        f"{GRANTS}/grants", headers={"x-user": "bob"}, params={"workspace": "notes"}
    )
    assert listed.status_code == 403


def test_a_workspaces_admin_lists_its_grants_but_not_the_tenants_members(
    client: TestClient,
) -> None:
    listed = client.get(
        f"{GRANTS}/grants", headers={"x-user": "dana"}, params={"workspace": "notes"}
    )
    assert listed.status_code == 200
    assert client.get(f"{GRANTS}/members", headers={"x-user": "dana"}).status_code == 403
