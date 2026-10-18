"""The test application's tracker: a dead-lettered run is filed, its link read back through
relayr, and a person's change there sets off a run of its own, which the app's scenarios rely on."""

import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.app.main import create_app
from tests.app.tracking import BASE_URL, FOLLOW_UP

REFLEXR = "/reflexr/v1/workspaces/notes"
ITEMS = "/relayr/v1/workspaces/notes/tracker/items"
BOB = {"x-user": "bob"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), headers={"X-Tenant": "acme"}) as client:
        yield client


def eventually[T](read: Callable[[], T | None], what: str) -> T:
    for _ in range(100):
        if (found := read()) is not None:
            return found
        time.sleep(0.1)
    raise AssertionError(what)


def runs(client: TestClient, rule: str) -> list[dict[str, Any]]:
    return client.get(f"{REFLEXR}/runs", headers=BOB, params={"rule": rule}).json()


def test_a_dead_lettered_run_is_filed_and_a_change_there_sets_off_a_run(
    client: TestClient,
) -> None:
    client.post(
        f"{REFLEXR}/events",
        headers=BOB,
        json={"event": {"type": "portalr:ticket.opened", "subject": "fail, to be filed"}},
    )
    item = eventually(
        lambda: next(iter(client.get(ITEMS, headers=BOB).json()["items"]), None),
        "the dead-lettered run was never filed",
    )
    assert item["name"] == "OPS-1"
    assert item["link"] == f"{BASE_URL}/ops/1"
    assert client.get(ITEMS).status_code == 401, "relayr's reads are the libraries' callers'"
    edited = client.post("/tracker/edits", json={"name": "OPS-1", "title": "Renamed"})
    assert edited.status_code == 204
    follow_up = eventually(
        lambda: next(iter(r for r in runs(client, FOLLOW_UP) if r["status"] == "succeeded"), None),
        "the change never set off a follow-up",
    )
    assert follow_up["correlation_id"] in item["chains"], "it joins the filing run's chain"
    missing = client.post("/tracker/edits", json={"name": "OPS-99", "title": "Renamed"})
    assert missing.status_code == 404
