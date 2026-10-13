"""The test application's restricted threads: hidden from the workspace, and shared by a grant.

The app restricts and shares a thread from its menu (portalr ADR-0022); this holds the test
application to what the scenarios rely on: a restricted thread is missing from an editor's reads,
a viewer's grant on it shows it again, read only, and an editor may not restrict one.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.app.main import create_app

THREADS = "/artifactr/v1/workspaces/notes"
GRANTS = "/grantr/v1/tenants/acme"
THREAD = {"kind": "thread", "workspace": "notes", "id": "thr_shared"}


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


def threads(client: TestClient, user: str) -> list[str]:
    listed = client.get(f"{THREADS}/threads", headers={"x-user": user}).json()
    return [thread["id"] for thread in listed]


def test_a_restricted_thread_is_hidden_until_shared_and_then_read_only(client: TestClient) -> None:
    created = command(client, "alice", {"type": "create_thread", "thread_id": "thr_shared"})
    assert created.status_code == 200
    restricted = client.post(
        f"{GRANTS}/restrictions", headers={"x-user": "alice"}, json={"on": THREAD}
    )
    assert restricted.status_code == 200
    assert "thr_shared" not in threads(client, "bob")

    shared = client.post(
        f"{GRANTS}/grants",
        headers={"x-user": "alice"},
        json={"role": "viewer", "on": THREAD, "to": {"kind": "user", "id": "bob"}},
    )
    assert shared.status_code == 201
    assert "thr_shared" in threads(client, "bob")
    posted = command(
        client, "bob", {"type": "post_message", "thread_id": "thr_shared", "content": "hi"}
    )
    assert posted.status_code == 403


def test_an_editor_may_not_restrict_a_thread(client: TestClient) -> None:
    command(client, "bob", {"type": "create_thread", "thread_id": "thr_shared"})
    refused = client.post(f"{GRANTS}/restrictions", headers={"x-user": "bob"}, json={"on": THREAD})
    assert refused.status_code == 403
    assert "grantr:restrict" in refused.json()["detail"]["message"]
