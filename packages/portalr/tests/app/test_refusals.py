"""The test application's grantr refuses what a viewer may not do, whatever the UI shows.

The app hides the actions grantr's checks refuse (portalr ADR-0018); this holds the server to
refusing them: vera, a viewer of acme's ``notes``, sends retry, skip and cancel on bob's
dead-lettered run, and each is refused.
"""

import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.app.main import create_app

RUNS = "/reflexr/v1/workspaces/notes"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), headers={"X-Tenant": "acme"}) as client:
        yield client


def dead_run(client: TestClient) -> str:
    """Publish a ticket that fails, as bob, and wait for its run to be dead-lettered."""
    published = client.post(
        f"{RUNS}/events",
        headers={"x-user": "bob"},
        json={"event": {"type": "portalr:ticket.opened", "subject": "fail on purpose"}},
    )
    seq = published.json()[0]["seq"]
    for _ in range(100):
        runs = client.get(f"{RUNS}/runs", headers={"x-user": "bob"}).json()
        dead = [run["id"] for run in runs if seq in run["matched"] and run["status"] == "dead"]
        if dead:
            return dead[0]
        time.sleep(0.1)
    raise AssertionError("the run was never dead-lettered")


@pytest.mark.parametrize("command", ["retry_run", "skip_run", "cancel_run"])
def test_a_viewer_is_refused_each_run_action(client: TestClient, command: str) -> None:
    run = dead_run(client)
    refused = client.post(
        f"{RUNS}/commands",
        headers={"x-user": "vera"},
        json={
            "type": "command",
            "command_id": f"vera-{command}",
            "command": {"type": command, "run_id": run},
        },
    )
    assert refused.status_code == 403
    assert refused.json()["rejection"]["type"] == "forbidden"
    assert f"reflexr:{command}" in refused.json()["rejection"]["message"]


def test_an_editor_is_not(client: TestClient) -> None:
    run = dead_run(client)
    retried = client.post(
        f"{RUNS}/commands",
        headers={"x-user": "bob"},
        json={
            "type": "command",
            "command_id": "bob-retry",
            "command": {"type": "retry_run", "run_id": run},
        },
    )
    assert retried.status_code == 200
