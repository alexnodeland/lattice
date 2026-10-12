"""The test application's stored rules: a workspace's admin installs one, and its runs succeed.

The Rules area installs, updates and archives stored rules (portalr ADR-0020); this holds the
test application to running them, as the rule, and to refusing an editor who tries.
"""

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.app.main import create_app

REFLEXR = "/reflexr/v1/workspaces/notes"

RULE = {
    "name": "tickets:echo",
    "description": "A ticket was opened: triage it again.",
    "when": {
        "filter": {"kind": "on", "types": ["portalr:ticket.opened"]},
        "throttle": {"at_most": 10, "per": "PT1H"},
    },
    "then": {"action": "triage"},
    "ordering": "none",
    "timeout": "PT30S",
}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), headers={"X-Tenant": "acme"}) as client:
        yield client


def install(client: TestClient, user: str) -> Any:
    return client.post(
        f"{REFLEXR}/commands",
        headers={"x-user": user},
        json={
            "type": "command",
            "command_id": f"{user}-install",
            "command": {"type": "install_rule", "rule": RULE},
        },
    )


def test_a_stored_rules_run_succeeds_as_the_rule(client: TestClient) -> None:
    assert install(client, "alice").status_code == 200
    published = client.post(
        f"{REFLEXR}/events",
        headers={"x-user": "bob"},
        json={"event": {"type": "portalr:ticket.opened", "subject": "a stored rule's"}},
    )
    seq = published.json()[0]["seq"]
    for _ in range(100):
        runs = client.get(
            f"{REFLEXR}/runs", headers={"x-user": "bob"}, params={"rule": RULE["name"]}
        ).json()
        if [run for run in runs if seq in run["matched"] and run["status"] == "succeeded"]:
            return
        time.sleep(0.1)
    raise AssertionError("the stored rule's run never succeeded")


def test_an_editor_may_not_install_one(client: TestClient) -> None:
    refused = install(client, "bob")
    assert refused.status_code == 403
    assert "reflexr:install_rule" in refused.json()["rejection"]["message"]


def test_the_schedule_is_listed(client: TestClient) -> None:
    schedules = client.get(f"{REFLEXR}/schedules", headers={"x-user": "bob"}).json()
    assert [schedule["schedule"] for schedule in schedules] == ["portalr:digest"]
