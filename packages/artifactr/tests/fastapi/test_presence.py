"""Presence over the thread protocol: watching an artifact, and what the others there are told
(lattice RFC-0006, artifactr ADR-0093)."""

import asyncio
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai import Agent
from starlette.testclient import WebSocketTestSession

from artifactr.agent import Runner, Session
from artifactr.core import (
    Actor,
    InvalidState,
    PeerLeft,
    PeerPresence,
    TenantId,
    UserActor,
    Visibility,
    WorkspaceId,
)
from artifactr.fastapi import artifactr_router
from artifactr.fastapi.presence import LocalPresence, Room
from artifactr.workspace import Access, InMemoryStorage, Workspaces, integration_gate
from tests.agent.conftest import Script
from tests.artifact_types import Note
from tests.fastapi.conftest import Latch, closing, command, hello, resolve_actor
from tests.workspace.gating import NOTES, Switch, key_of

STREAM = "/v1/workspaces/w1/stream"


class Grants:
    """Vera may view and not edit; Hal sees nothing of ``n1``; Olga may read nothing."""

    def __init__(self) -> None:
        self.readers: set[str] = {"alice", "bob", "carol", "vera", "hal"}
        self.broken = False
        self.hung = False
        """Whether authorize never answers, as a grants store that hangs doesn't."""
        """Whether authorize fails, as a grants store that can't be reached does."""

    async def authorize(
        self, tenant_id: TenantId, workspace_id: WorkspaceId | None, actor: Actor, access: Access
    ) -> bool:
        name = actor.participant.removeprefix("user:")
        if self.broken:
            raise RuntimeError("the grants can't be read")
        if self.hung:
            await asyncio.Event().wait()
        if access.action == "artifactr:edit_artifact":
            return name not in {"vera"} and name in self.readers
        if access.action == "artifactr:read_artifacts":
            return name in self.readers
        return True

    async def hidden(self, tenant: str, workspace: str, actor: Any) -> Visibility:
        hal = actor == UserActor(id="hal")
        return Visibility(artifacts=frozenset({"n1"}) if hal else frozenset())


@pytest.fixture
def grants() -> Grants:
    return Grants()


@pytest.fixture
def switch() -> Switch:
    return Switch()


def _app(grants: Grants, switch: Switch, **options: Any) -> FastAPI:
    agent: Agent[Session[Latch], Any] = Agent(Script().model, deps_type=Session[Latch])
    workspaces = Workspaces(
        InMemoryStorage(),
        types=[Note],
        authorize=grants.authorize,
        hidden=grants.hidden,
        gate=integration_gate(switch, key_of),
    )
    runner = Runner(agent, app=Latch())
    app = closing(runner)
    router = artifactr_router(workspaces, runner, resolve_actor=resolve_actor, **options)
    app.include_router(router, prefix="/v1")
    return app


@pytest.fixture
def client(grants: Grants, switch: Switch) -> Iterator[TestClient]:
    with TestClient(_app(grants, switch)) as client:
        made = command("c0", type="create_artifact", artifact_id="n1", kind="note", data={})
        assert client.post("/v1/workspaces/w1/commands", json=made).status_code == 200
        yield client


@contextmanager
def _watching(
    client: TestClient, user: str, artifact: str = "n1"
) -> Iterator[tuple[WebSocketTestSession, dict[str, Any]]]:
    with client.websocket_connect(STREAM, headers={"x-user": user}) as ws:
        ws.send_json(hello(from_head=True, events=False))
        _until(ws, "replay_complete")
        ws.send_json(command(f"w-{user}", type="watch_artifact", artifact_id=artifact))
        result = _until(ws, "command_result")
        yield ws, result


def _until(ws: WebSocketTestSession, frame_type: str, limit: int = 50) -> dict[str, Any]:
    for _ in range(limit):
        frame = ws.receive_json()
        if frame["type"] == frame_type:
            return frame
    raise AssertionError(f"no {frame_type} frame")


def _presence(seq: int, artifact: str = "n1", **fields: Any) -> dict[str, Any]:
    return {"type": "presence", "artifact_id": artifact, "seq": seq, "base_version": 1, **fields}


def _settled(ws: WebSocketTestSession, mark: str = "mark") -> list[dict[str, Any]]:
    """Every frame the connection is sent before the answer to a command sent now."""
    ws.send_json(command(mark, type="unwatch_artifact", artifact_id="nothing"))
    frames: list[dict[str, Any]] = []
    while (frame := ws.receive_json()).get("command_id") != mark:
        frames.append(frame)
    return frames


def test_watchers_hear_each_other_stamped_by_the_server(client: TestClient) -> None:
    with _watching(client, "alice") as (alice, watching):
        assert watching["outcome"]["rights"] == "edit"
        assert (watching["outcome"]["type"], watching["outcome"]["artifact_id"]) == (
            "watching",
            "n1",
        )
        # A presence connection is sent no events: a note made now isn't.
        made = command("c9", type="create_artifact", artifact_id="n2", kind="note", data={})
        assert client.post("/v1/workspaces/w1/commands", json=made).status_code == 200
        assert [f["type"] for f in _settled(alice, "quiet")] == []
        with _watching(client, "bob") as (bob, _):
            bob.send_json(_presence(1, pointer={"x": 3, "y": 4}, selection=["a"]))
            heard = _until(alice, "peer_presence")
            assert (
                heard["actor"] == {"type": "user", "id": "bob", "name": None}
                or heard["actor"]["id"] == "bob"
            )
            assert (heard["pointer"]["x"], heard["selection"], heard["seq"]) == (3, ["a"], 1)
            # Carol, joining, is told at once what each one there last said.
            with _watching(client, "carol") as (carol, _):
                assert _until(carol, "peer_presence")["peer"] == heard["peer"]
            left = _until(alice, "peer_left")
            assert left["artifact_id"] == "n1"
        # Bob's connection closing is his leaving.
        assert _until(alice, "peer_left")["peer"] == heard["peer"]


def test_a_client_names_no_actor_of_its_own(client: TestClient) -> None:
    with _watching(client, "bob") as (bob, _):
        bob.send_json(_presence(1, actor={"type": "user", "id": "alice"}))
        assert _until(bob, "error")["message"].startswith("not a command or presence frame")


def test_unwatching_is_leaving(client: TestClient) -> None:
    with _watching(client, "alice") as (alice, _), _watching(client, "bob") as (bob, _):
        bob.send_json(_presence(1))
        peer = _until(alice, "peer_presence")["peer"]
        bob.send_json(command("u", type="unwatch_artifact", artifact_id="n1"))
        assert _until(bob, "command_result")["outcome"]["type"] == "recorded"
        assert _until(alice, "peer_left")["peer"] == peer
        bob.send_json(_presence(2))  # no longer watched: dropped
        assert [f["type"] for f in _settled(alice)] == []


def test_a_watch_is_a_read_a_hidden_artifact_missing_and_off_not_enabled(
    client: TestClient, switch: Switch
) -> None:
    with _watching(client, "hal") as (_, hidden), _watching(client, "hal", "n9") as (_, missing):
        assert hidden["rejection"]["type"] == missing["rejection"]["type"] == "not_found"
    with _watching(client, "olga") as (_, refused):
        assert refused["rejection"]["type"] == "not_found" or refused["ok"] is False
    switch.off.add(("tenant", "w1", NOTES))
    with _watching(client, "alice") as (_, off):
        assert off["rejection"]["type"] == "not_enabled"
    sent = client.post(
        "/v1/workspaces/w1/commands", json=command("r", type="watch_artifact", artifact_id="n1")
    )
    assert (sent.status_code, sent.json()["rejection"]["message"]) == (
        409,
        "watch_artifact needs a WebSocket",
    )


def test_a_viewer_points_but_edits_nothing(client: TestClient) -> None:
    with _watching(client, "alice") as (alice, _), _watching(client, "vera") as (vera, watching):
        assert watching["outcome"]["rights"] == "view"
        vera.send_json(_presence(1, editing=[{"id": "x", "type": "rectangle"}]))
        vera.send_json(_presence(2, editing=[{"id": "x", "type": "rectangle"}]))
        errors = [f for f in _settled(vera) if f["type"] == "error"]
        assert [e["message"] for e in errors] == ["presence dropped: this watch may only view"]
        vera.send_json(_presence(3, pointer={"x": 1, "y": 1}))
        heard = _until(alice, "peer_presence")
        assert (heard["seq"], heard["editing"]) == (3, [])


def test_presence_past_its_size_or_pace_is_dropped_and_said_once(client: TestClient) -> None:
    with _watching(client, "alice") as (alice, _), _watching(client, "bob") as (bob, _):
        bob.send_json(_presence(1, editing=[{"id": "x", "text": "a" * 70_000}]))
        for seq in range(2, 60):
            bob.send_json(_presence(seq))
        errors = [f for f in _settled(bob) if f["type"] == "error"]
        assert len(errors) == 1
        heard = [f for f in _settled(alice, "a") if f["type"] == "peer_presence"]
        assert heard, "the latest frame is sent"
        assert heard[-1]["seq"] <= 31, "past thirty a second, frames are dropped"


def test_a_flood_of_presence_never_closes_a_connection_that_keeps_up_with_events(
    grants: Grants, switch: Switch
) -> None:
    with TestClient(_app(grants, switch, outbox_size=4)) as client:
        made = command("c0", type="create_artifact", artifact_id="n1", kind="note", data={})
        client.post("/v1/workspaces/w1/commands", json=made)
        with _watching(client, "alice") as (alice, _):
            peers = [
                client.websocket_connect(STREAM, headers={"x-user": f"p{i}"}) for i in range(1)
            ]
            del peers
            with _watching(client, "bob") as (bob, _):
                for seq in range(1, 30):
                    bob.send_json(_presence(seq, pointer={"x": seq, "y": 0}))
                _settled(bob)
                frames = _settled(alice)
                seqs = [f["seq"] for f in frames if f["type"] == "peer_presence"]
                assert seqs == sorted(seqs)
                assert seqs[-1] == 29, "the latest is sent: the connection stays open"


def test_a_watch_ends_once_its_rights_are_gone(grants: Grants, switch: Switch) -> None:
    with TestClient(_app(grants, switch, watch_recheck=0.05)) as client:
        made = command("c0", type="create_artifact", artifact_id="n1", kind="note", data={})
        client.post("/v1/workspaces/w1/commands", json=made)
        with _watching(client, "alice") as (alice, _), _watching(client, "bob") as (bob, watching):
            own = watching["outcome"]["peer"]
            alice.send_json(_presence(1))
            peer = _until(bob, "peer_presence")["peer"]
            time.sleep(0.2)  # the rights are read again, and still hold
            alice.send_json(_presence(2))
            assert _until(bob, "peer_presence")["seq"] == 2
            switch.off.add(("tenant", "w1", NOTES))
            # Told the watch ended: an error, sent before presence is, that everyone left, and that
            # it did, by its own peer.
            ended = [bob.receive_json() for _ in range(3)]
            assert sorted(f["type"] for f in ended) == ["error", "peer_left", "peer_left"]
            assert {f["peer"] for f in ended if f["type"] == "peer_left"} == {peer, own}
            alice.send_json(_presence(3))  # bob no longer watches: he hears nothing
            assert [f["type"] for f in _settled(bob)] == []
        grants.readers.discard("carol")
        with _watching(client, "carol") as (_, refused):
            assert refused["ok"] is False


def test_a_watch_may_be_asked_again_and_says_the_rights_now(client: TestClient) -> None:
    with _watching(client, "alice") as (alice, _):
        alice.send_json(command("again", type="watch_artifact", artifact_id="n1"))
        assert _until(alice, "command_result")["outcome"]["rights"] == "edit"


# ─── the in-process channel ──────────────────────────────────────────────────


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


ROOM: Room = ("tenant", "w1", "n1")


def _frame(peer: str, seq: int) -> PeerPresence:
    return PeerPresence(
        artifact_id="n1", peer=peer, actor=UserActor(id=peer), seq=seq, base_version=1
    )


def test_a_silent_peer_is_announced_as_left_and_is_back_when_it_speaks() -> None:
    clock = Clock()
    rooms = LocalPresence(clock=clock)
    told: dict[str, list[PeerPresence | PeerLeft]] = {"a": [], "b": []}
    rooms.join(ROOM, "a", lambda frame, _: told["a"].append(frame))
    rooms.join(ROOM, "b", lambda frame, _: told["b"].append(frame))
    rooms.say(ROOM, _frame("a", 1))
    clock.now = 11
    rooms.say(ROOM, _frame("b", 1))
    assert told["b"] == [_frame("a", 1), PeerLeft(artifact_id="n1", peer="a")]
    assert rooms.join(ROOM, "c", lambda *_: None) == [_frame("b", 1)], "a is silent: not here"
    rooms.say(ROOM, _frame("a", 2))
    assert told["b"][-1] == _frame("a", 2)
    rooms.say(ROOM, _frame("z", 1))  # never joined: says nothing
    rooms.leave(ROOM, "z")
    for peer in ("a", "b", "c"):
        rooms.leave(ROOM, peer)
    assert rooms.join(ROOM, "d", lambda *_: None) == []


def test_a_room_is_full_at_its_most() -> None:
    rooms = LocalPresence(most=2)
    rooms.join(ROOM, "a", lambda *_: None)
    rooms.join(ROOM, "b", lambda *_: None)
    rooms.join(ROOM, "a", lambda *_: None)  # one already there joins again
    with pytest.raises(InvalidState, match="at most 2"):
        rooms.join(ROOM, "c", lambda *_: None)


def test_a_full_room_and_too_many_watches_are_refused(grants: Grants, switch: Switch) -> None:
    with TestClient(_app(grants, switch, presence=LocalPresence(most=1))) as client:
        for at in range(21):
            made = command(
                f"c{at}", type="create_artifact", artifact_id=f"n{at}", kind="note", data={}
            )
            client.post("/v1/workspaces/w1/commands", json=made)
        with (
            _watching(client, "alice", "n0") as (alice, _),
            _watching(client, "bob", "n0") as (
                _,
                full,
            ),
        ):
            assert full["rejection"]["type"] == "invalid_state"
            for at in range(1, 20):
                alice.send_json(command(f"w{at}", type="watch_artifact", artifact_id=f"n{at}"))
                assert _until(alice, "command_result")["ok"] is True
            alice.send_json(command("w20", type="watch_artifact", artifact_id="n20"))
            refused = _until(alice, "command_result")
            assert (refused["ok"], refused["rejection"]["type"]) == (False, "invalid_state")
            # One unwatched makes room for another.
            alice.send_json(command("u1", type="unwatch_artifact", artifact_id="n1"))
            assert _until(alice, "command_result")["ok"] is True
            alice.send_json(command("w21", type="watch_artifact", artifact_id="n20"))
            assert _until(alice, "command_result")["ok"] is True


@pytest.mark.parametrize("failure", ["broken", "hung"])
def test_rights_that_cant_be_read_in_time_end_the_watch(
    grants: Grants, switch: Switch, failure: str
) -> None:
    with TestClient(_app(grants, switch, watch_recheck=0.05)) as client:
        made = command("c0", type="create_artifact", artifact_id="n1", kind="note", data={})
        client.post("/v1/workspaces/w1/commands", json=made)
        with _watching(client, "bob") as (bob, watching):
            setattr(grants, failure, True)  # it fails closed: never watching on, unchecked
            frames = [bob.receive_json() for _ in range(2)]
            assert sorted(f["type"] for f in frames) == ["error", "peer_left"]
            [left] = [f for f in frames if f["type"] == "peer_left"]
            assert left["peer"] == watching["outcome"]["peer"]
