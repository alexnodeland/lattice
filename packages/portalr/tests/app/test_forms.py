"""The test application's agent asks a form through artifactr.ui, which its checks hold.

bob posts ``form``: the agent asks for leave, and the run pauses on ``ask_form``. An answer the
form refuses is refused with the field its error names, as portalr shows it under that field
(lattice RFC-0005); the answer it takes resumes the run, which says what it was given, and a
second answer is refused as answered already, with no reason of artifactr.ui's own.
"""

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.app.main import create_app

NOTES = "/artifactr/v1/workspaces/notes"
BOB = {"x-user": "bob"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), headers={"X-Tenant": "acme"}) as client:
        yield client


def send(client: TestClient, command: dict[str, Any], name: str) -> Any:
    """Send one command as bob, and the server's answer."""
    return client.post(
        f"{NOTES}/commands",
        headers=BOB,
        json={"type": "command", "command_id": name, "command": command},
    )


def events(client: TestClient, kind: str) -> list[dict[str, Any]]:
    """The workspace's events of one type, as bob reads them, waiting for the first."""
    for _ in range(100):
        frames = client.get(f"{NOTES}/events", headers=BOB).json()
        found = [frame["event"] for frame in frames if frame["event"]["type"] == kind]
        if found:
            return found
        time.sleep(0.05)
    raise AssertionError(f"no {kind} came")


def test_a_form_is_refused_by_its_field_then_answered_once(client: TestClient) -> None:
    assert send(client, {"type": "create_thread", "thread_id": "thr_leave"}, "c1").is_success
    posted = {"type": "post_message", "thread_id": "thr_leave", "content": "form please"}
    assert send(client, posted, "c2").is_success
    paused = events(client, "run_paused")[0]
    request = paused["requests"][0]
    assert request["tool_name"] == "ask_form"
    answer = {"type": "answer_deferred", "run_id": paused["run_id"]}
    answer["tool_call_id"] = request["tool_call_id"]

    refused = send(client, {**answer, "answer": {"days": 40}}, "c3")
    rejection = refused.json()["rejection"]
    assert rejection["type"] == "validation_failed"
    assert [error["loc"][-1] for error in rejection["errors"]] == ["days"]

    assert send(client, {**answer, "answer": {"days": 3}}, "c4").is_success
    said = [event["content"] for event in events(client, "message_posted")]
    for _ in range(100):
        if "Done: 3 working days off" in said:
            break
        time.sleep(0.05)
        said = [event["content"] for event in events(client, "message_posted")]
    assert "Done: 3 working days off" in said

    again = send(client, {**answer, "answer": {"days": 2}}, "c5").json()["rejection"]
    assert again["type"] == "invalid_state"
    assert "reason" not in again
