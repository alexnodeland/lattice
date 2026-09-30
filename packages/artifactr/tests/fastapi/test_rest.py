"""REST: commands through the shared handler, and reads."""

from typing import Any

from fastapi.testclient import TestClient

from tests.agent.conftest import Script, call, say
from tests.fastapi.conftest import build, command, wait_for

BASE = "/v1/workspaces/w1"


def test_a_command_is_carried_out_through_the_runner(client: TestClient) -> None:
    create = command("c1", type="create_thread", thread_id="t1", title="Launch")
    first = client.post(f"{BASE}/commands", json=create)
    assert first.json() == {
        "type": "command_result",
        "command_id": "c1",
        "ok": True,
        "outcome": {"type": "recorded", "seq": 1, "run_id": None},
        "rejection": None,
    }
    again = client.post(f"{BASE}/commands", json=create)
    assert again.json() == first.json(), "a repeated command id returns the same result"


def test_rejections_map_to_status_codes(client: TestClient) -> None:
    missing = client.post(
        f"{BASE}/commands", json=command("c1", type="post_message", thread_id="t9", content="hi")
    )
    assert missing.status_code == 404
    assert missing.json()["rejection"]["type"] == "not_found"
    client.post(f"{BASE}/commands", json=command("c2", type="create_thread", thread_id="t1"))
    exists = client.post(
        f"{BASE}/commands", json=command("c3", type="create_thread", thread_id="t1")
    )
    assert exists.status_code == 409
    watch = client.post(f"{BASE}/commands", json=command("c4", type="watch_run", run_id="r1"))
    assert watch.status_code == 409
    assert watch.json()["rejection"]["message"] == "watch_run needs a WebSocket"
    unknown = client.post(
        f"{BASE}/commands", json=command("c5", type="create_artifact", kind="x", data={})
    )
    assert unknown.status_code == 404


def test_authentication_and_authorization(client: TestClient) -> None:
    assert client.get(f"{BASE}/threads", headers={"x-token": "bad"}).status_code == 401
    refused = client.get("/v1/workspaces/secret/threads")
    assert refused.status_code == 403
    assert refused.json()["detail"] == {
        "type": "forbidden",
        "message": "this workspace is not yours to use",
    }, "a rejection's payload, as every REST error"


def test_reads(client: TestClient) -> None:
    def post(command_id: str, **fields: Any) -> None:
        client.post(f"{BASE}/commands", json=command(command_id, **fields))

    post("c1", type="create_thread", thread_id="t1")
    post("c2", type="create_thread", thread_id="t2")
    post("c3", type="create_artifact", artifact_id="n1", kind="note", data={"text": "Friday"})
    post("c4", type="create_artifact", artifact_id="n2", kind="note", data={})
    post(
        "c5",
        type="edit_artifact",
        artifact_id="n1",
        base_version=1,
        patch={"kind": "text_edits", "edits": [{"old": "Friday", "new": "Monday"}]},
    )
    post("c6", type="archive_artifact", artifact_id="n2", base_version=1)
    post("c7", type="post_message", thread_id="t2", content="elsewhere")
    assert [a["id"] for a in client.get(f"{BASE}/artifacts").json()] == ["n1"]
    everything = client.get(f"{BASE}/artifacts", params={"include_archived": True, "kind": "note"})
    assert [a["id"] for a in everything.json()] == ["n1", "n2"]
    assert client.get(f"{BASE}/artifacts", params={"kind": "checklist"}).json() == []
    n1 = client.get(f"{BASE}/artifacts/n1").json()
    assert (n1["kind"], n1["data"]["text"]) == ("note", "Monday")
    assert client.get(f"{BASE}/artifacts/nope").status_code == 404
    assert [r["version"] for r in client.get(f"{BASE}/artifacts/n1/revisions").json()] == [1, 2]
    assert client.get(f"{BASE}/artifacts/nope/revisions").status_code == 404
    only_t1 = client.get(f"{BASE}/events", params={"thread_id": "t1", "after_seq": 0, "limit": 10})
    assert "message_posted" not in [e["event"]["type"] for e in only_t1.json()]
    assert [t["id"] for t in client.get(f"{BASE}/threads").json()] == ["t1", "t2"]
    assert client.get(f"{BASE}/threads/t1").json()["mode"] == "edit"
    assert client.get(f"{BASE}/threads/t9").status_code == 404
    assert client.get(f"{BASE}/proposals").json() == []
    assert client.get(f"{BASE}/proposals", params={"status": "accepted"}).json() == []
    assert client.get(f"{BASE}/runs/r1").status_code == 404


def test_the_log_is_read_from_its_end_and_backwards(client: TestClient) -> None:
    for number, thread_id in enumerate(("t1", "t2", "t3", "t4"), start=1):
        client.post(
            f"{BASE}/commands",
            json=command(f"c{number}", type="create_thread", thread_id=thread_id),
        )

    def seqs(**params: int | list[str]) -> list[int]:
        return [e["seq"] for e in client.get(f"{BASE}/events", params=params).json()]

    assert seqs(last=2) == [3, 4]
    assert seqs(last=2, thread_id=["t1", "t3"]) == [1, 3]
    assert seqs(last=2, before_seq=3) == [1, 2]
    assert seqs(after_seq=1, before_seq=4) == [2, 3]
    both = client.get(f"{BASE}/events", params={"limit": 1, "last": 1})
    assert (both.status_code, both.json()["detail"]) == (
        422,
        {"type": "validation_failed", "message": "give limit or last, not both", "errors": []},
    )
    assert client.get(f"{BASE}/events", params={"before_seq": -1}).status_code == 422


def test_a_posted_message_runs_the_agent() -> None:
    app, _ = build(
        Script(call("create_artifact", kind="note", data={"text": "Plan"}), say("Done."))
    )
    with TestClient(app) as client:
        client.post(f"{BASE}/commands", json=command("c1", type="create_thread", thread_id="t1"))
        posted = client.post(
            f"{BASE}/commands",
            json=command("c2", type="post_message", thread_id="t1", content="Draft"),
        )
        outcome = posted.json()["outcome"]
        assert outcome["type"] == "recorded"
        run_id = outcome["run_id"]

        def ended() -> bool:
            return "run_ended" in [e["event"]["type"] for e in client.get(f"{BASE}/events").json()]

        wait_for(ended)
        assert {e["run_id"] for e in client.get(f"{BASE}/events").json() if e["run_id"]} == {run_id}
        assert client.get(f"{BASE}/runs/{run_id}").json()["status"] == "completed"
        stop = client.post(f"{BASE}/commands", json=command("c3", type="stop_run", run_id=run_id))
        assert stop.status_code == 404, "a finished run cannot be stopped"
        other = client.post(
            "/v1/workspaces/w2/commands", json=command("c4", type="stop_run", run_id=run_id)
        )
        assert other.json()["rejection"]["entity"] == "run", (
            "runs of other workspaces are invisible"
        )


def test_a_notice_starts_no_run_and_reads_as_a_notice(client: TestClient) -> None:
    client.post(f"{BASE}/commands", json=command("c1", type="create_thread", thread_id="t1"))
    notice = command("c2", type="post_message", thread_id="t1", content="Deployed", kind="notice")
    posted = client.post(f"{BASE}/commands", json=notice)
    assert posted.json()["outcome"] == {"type": "recorded", "seq": 2, "run_id": None}
    [event] = client.get(f"{BASE}/events", params={"after_seq": 1}).json()
    assert (event["event"]["type"], event["event"]["kind"]) == ("message_posted", "notice")


def test_feedback_is_a_command_like_any_other(client: TestClient) -> None:
    client.post(f"{BASE}/commands", json=command("c1", type="create_thread", thread_id="t1"))
    feedback = command(
        "c2",
        type="give_feedback",
        feedback_type="helpfulness",
        target={"kind": "thread", "thread_id": "t1"},
        value={"rating": 5},
    )
    given = client.post(f"{BASE}/commands", json=feedback)
    assert given.json()["outcome"] == {"type": "recorded", "seq": 2, "run_id": None}
    [event] = client.get(f"{BASE}/events", params={"after_seq": 1}).json()
    assert event["event"]["type"] == "feedback_given"
    assert event["actor"]["id"] == "alice"
    invalid = dict(feedback, command_id="c3")
    invalid["command"] = dict(feedback["command"], value={"rating": 0})
    assert client.post(f"{BASE}/commands", json=invalid).status_code == 422
