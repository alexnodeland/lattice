"""The test application's native files: the agent drafts a document, and waits out a check-out.

The app's scenarios check documents out and in (lattice RFC-0003, phase 4); this holds the test
application to what they rely on: ``draft`` makes a document the person who asked has, and
``revise`` is told who has it checked out and to plan again after the check-in, and once it is
checked in, proposes its edit.
"""

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from artifactr.files.app import FakeApp
from tests.app.editor import app as editor_app
from tests.app.main import create_app, editors

ARTIFACTR = "/artifactr/v1/workspaces/notes"
BOB = {"x-user": "bob"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), headers={"X-Tenant": "acme"}) as client:
        yield client


def said(client: TestClient, run: str) -> list[str]:
    """What the agent has said in a run, in order."""
    events = client.get(f"{ARTIFACTR}/events", headers=BOB).json()
    return [
        str(each["event"]["content"])
        for each in events
        if each["run_id"] == run and each["event"]["type"] == "message_posted"
    ]


def answer(client: TestClient, thread: str, prompt: str) -> str:
    """Post a prompt as bob, and wait for the agent's answer to it, in the run it started."""
    command = {"type": "post_message", "thread_id": thread, "content": prompt}
    sent = {"type": "command", "command_id": f"bob-{time.monotonic()}", "command": command}
    posted = client.post(f"{ARTIFACTR}/commands", headers=BOB, json=sent)
    assert posted.status_code == 200, posted.text
    run = posted.json()["outcome"]["run_id"]
    for _ in range(100):
        if answers := said(client, run):
            return answers[-1]
        time.sleep(0.1)
    raise AssertionError(f"the agent never answered {prompt!r}")


def test_a_drafted_document_waits_out_a_check_out_then_takes_a_proposal(
    client: TestClient,
) -> None:
    started = {"type": "create_thread", "thread_id": "thr_docs"}
    command: dict[str, Any] = {"type": "command", "command_id": "bob-thread", "command": started}
    assert client.post(f"{ARTIFACTR}/commands", headers=BOB, json=command).status_code == 200
    drafted = answer(client, "thr_docs", "draft the brief")
    document = drafted.removeprefix("Drafted ")
    status = client.get(f"{ARTIFACTR}/files/{document}", headers=BOB).json()
    assert (status["name"], status["pages"]) == ("brief.docx", 2)
    assert status["outline"].startswith("Brief\nBrief starts on Monday.")
    checkout = client.post(f"{ARTIFACTR}/files/{document}/checkouts", headers=BOB).json()

    busy = answer(client, "thr_docs", f"revise {document}")
    assert "checked out by user:bob" in busy
    assert "plan again once it is checked in" in busy

    edited = FakeApp.file("Brief", "Brief starts on Tuesday.")
    url = f"{ARTIFACTR}/checkouts/{checkout['id']}/file"
    assert client.put(url, content=edited, headers=BOB).json()["outcome"] == "applied"
    proposed = answer(client, "thr_docs", f"revise {document}")
    assert proposed.startswith("Done: Proposed as ")


def test_the_editor_is_a_stand_in_served_under_its_own_policy() -> None:
    editor = TestClient(editor_app)
    page = editor.get("/")
    policy = page.headers["content-security-policy"]
    assert "'sha256-" in policy, "its inline script, by its hash"
    assert policy.startswith("default-src 'self' blob:")
    assert editor.get("/app-1a2b_bg.wasm").headers["content-type"] == "application/wasm"


def test_the_application_names_the_editor_its_environment_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PORTALR_EDITOR_URL", "http://127.0.0.1:8001/")
    assert editors() == {"files:wordcraft": "http://127.0.0.1:8001/"}
    monkeypatch.delenv("PORTALR_EDITOR_URL")
    assert editors() == {}
