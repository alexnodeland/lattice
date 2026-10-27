"""The thread protocol over WebSocket."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import ModelResponse, TextPart
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from artifactr.core import (
    Actor,
    AgentActor,
    ErrorFrame,
    LiveFrame,
    RunStarted,
    TenantId,
    TextDelta,
    ThinkingDelta,
    UserActor,
    Visibility,
    WorkspaceId,
)
from artifactr.fastapi import stream
from artifactr.workspace import InMemoryStorage, Workspace, Workspaces, integration_gate
from tests.agent.conftest import Script, ask, call, say
from tests.fastapi.conftest import Latch, build, command, hello, wait_for
from tests.workspace.gating import NOTES, Switch, key_of

STREAM = "/v1/workspaces/w1/stream"


def _post(client: TestClient, command_id: str, **body: Any) -> None:
    client.post("/v1/workspaces/w1/commands", json=command(command_id, **body))


def _until_event(
    ws: WebSocketTestSession, event_type: str, limit: int = 200
) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for _ in range(limit):
        frame = ws.receive_json()
        frames.append(frame)
        if frame["type"] == "event" and frame["event"]["type"] == event_type:
            return frames
    raise AssertionError(f"no {event_type} event in {frames}")


def _receive_until(
    ws: WebSocketTestSession, frame_type: str, limit: int = 50
) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for _ in range(limit):
        frame = ws.receive_json()
        frames.append(frame)
        if frame["type"] == frame_type:
            return frames
    raise AssertionError(f"no {frame_type} frame in {frames}")


def test_hello_welcome_replay_then_live(client: TestClient) -> None:
    _post(client, "c1", type="create_thread", thread_id="t1")
    _post(client, "c2", type="create_thread", thread_id="t2")
    with client.websocket_connect(STREAM, subprotocols=["artifactr.v1"]) as ws:
        assert ws.accepted_subprotocol == "artifactr.v1"
        ws.send_json(hello(resume_after_seq=0, threads=["t1"]))
        welcome = ws.receive_json()
        assert (welcome["type"], welcome["head_seq"], welcome["reset"]) == ("welcome", 2, False)
        replayed = _receive_until(ws, "replay_complete")
        assert [f.get("seq") for f in replayed] == [1, None], "t2's thread_created is filtered"
        assert replayed[-1] == {"type": "replay_complete", "up_to_seq": 2}
        _post(client, "c3", type="set_thread_mode", thread_id="t2", mode="suggest")  # not followed
        _post(client, "c4", type="create_artifact", artifact_id="n1", kind="note", data={})
        live = ws.receive_json()
        assert (live["type"], live["seq"], live["event"]["type"]) == (
            "event",
            4,
            "artifact_created",
        )


def test_an_up_to_date_client_gets_replay_complete_at_once(client: TestClient) -> None:
    _post(client, "c1", type="create_thread", thread_id="t1")
    with client.websocket_connect(STREAM) as ws:
        assert ws.accepted_subprotocol is None
        ws.send_json(hello(resume_after_seq=1))
        assert ws.receive_json()["type"] == "welcome"
        assert ws.receive_json() == {"type": "replay_complete", "up_to_seq": 1}


def test_a_client_from_the_head_replays_nothing_and_follows_live(client: TestClient) -> None:
    _post(client, "c1", type="create_thread", thread_id="t1")
    _post(client, "c2", type="create_artifact", artifact_id="n1", kind="note", data={})
    with client.websocket_connect(STREAM) as ws:
        ws.send_json(hello(from_head=True, threads=["t2"]))
        welcome = ws.receive_json()
        assert (welcome["head_seq"], welcome["reset"]) == (2, False)
        assert ws.receive_json() == {"type": "replay_complete", "up_to_seq": 2}
        _post(client, "c3", type="set_thread_mode", thread_id="t1", mode="suggest")  # not followed
        _post(client, "c4", type="create_thread", thread_id="t2")
        live = ws.receive_json()
        assert (live["type"], live["seq"], live["event"]["type"]) == (
            "event",
            4,
            "thread_created",
        )


def test_a_client_from_the_head_cannot_also_resume(client: TestClient) -> None:
    _post(client, "c1", type="create_thread", thread_id="t1")
    with client.websocket_connect(STREAM) as ws:
        ws.send_json(hello(from_head=True, resume_after_seq=1))
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert (closed.value.code, closed.value.reason) == (
        4400,
        "from_head replays nothing, so resume_after_seq must be 0",
    )


def test_a_client_ahead_of_the_log_is_reset(client: TestClient) -> None:
    with client.websocket_connect(STREAM) as ws:
        ws.send_json(hello(resume_after_seq=99))
        assert ws.receive_json()["reset"] is True


@pytest.mark.parametrize(
    ("path", "headers", "code"),
    [
        (STREAM, {"x-token": "bad"}, 4401),
        (STREAM, {"x-token": "unnamed"}, 4400),
        (STREAM, {"x-token": "stranger"}, 4403),
        ("/v1/workspaces/secret/stream", {}, 4403),
    ],
)
def test_refused_connections_are_closed_with_a_reason(
    client: TestClient, path: str, headers: dict[str, str], code: int
) -> None:
    with (
        client.websocket_connect(path, headers=headers) as ws,
        pytest.raises(WebSocketDisconnect) as closed,
    ):
        ws.receive_json()
    assert closed.value.code == code


@pytest.mark.parametrize(
    ("first", "code"),
    [({"type": "command"}, 4400), (hello() | {"protocol": "artifactr.v0"}, 4400)],
)
def test_a_bad_first_frame_closes_the_connection(
    client: TestClient, first: dict[str, Any], code: int
) -> None:
    with client.websocket_connect(STREAM) as ws:
        ws.send_json(first)
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == code


def test_a_client_that_may_not_read_the_log_is_closed_before_welcome(client: TestClient) -> None:
    with client.websocket_connect("/v1/workspaces/sealed/stream") as ws:
        ws.send_json(hello())
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert (closed.value.code, closed.value.reason) == (
        4403,
        "artifactr:read_events is refused in this workspace",
    )


def test_hello_must_arrive_in_time() -> None:
    app, _ = build(Script(), hello_timeout=0.05)
    with TestClient(app) as client, client.websocket_connect(STREAM) as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 4408


def test_commands_invalid_frames_and_rejections(client: TestClient) -> None:
    with client.websocket_connect(STREAM) as ws:
        ws.send_json(hello())
        _receive_until(ws, "replay_complete")
        ws.send_json(command("c1", type="create_thread", thread_id="t1"))
        frames = [ws.receive_json(), ws.receive_json()]
        [result] = [f for f in frames if f["type"] == "command_result"]
        assert (result["command_id"], result["ok"]) == ("c1", True)
        ws.send_json({"type": "nonsense"})
        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["message"].startswith("not a command or presence frame: ")
        ws.send_json(command("c2", type="watch_run", run_id="r9"))
        rejected = ws.receive_json()
        assert (rejected["ok"], rejected["rejection"]["type"]) == (False, "not_found")


def test_a_command_an_integration_switched_off_refuses() -> None:
    switch = Switch()
    switch.off.add(("tenant", "w1", NOTES))
    app, _ = build(Script(), gate=integration_gate(switch, key_of))
    with TestClient(app) as client, client.websocket_connect(STREAM) as ws:
        ws.send_json(hello())
        _receive_until(ws, "replay_complete")
        ws.send_json(command("c1", type="create_artifact", kind="note", data={}))
        rejected = ws.receive_json()
        assert (rejected["ok"], rejected["rejection"]["integration"]) == (False, NOTES)


def test_a_notice_arrives_as_a_notice(client: TestClient) -> None:
    _post(client, "c1", type="create_thread", thread_id="t1")
    with client.websocket_connect(STREAM) as ws:
        ws.send_json(hello(from_head=True))
        _receive_until(ws, "replay_complete")
        notice = command("c2", type="post_message", thread_id="t1", content="Hi", kind="notice")
        ws.send_json(notice)
        frames = [ws.receive_json(), ws.receive_json()]
        [event] = [f["event"] for f in frames if f["type"] == "event"]
        [result] = [f for f in frames if f["type"] == "command_result"]
        assert (event["type"], event["kind"]) == ("message_posted", "notice")
        assert result["outcome"]["run_id"] is None, "it started no run"


def test_a_command_that_crashes_reports_an_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, runner = build(Script())

    async def explode(*args: Any) -> None:
        raise RuntimeError("bug")

    monkeypatch.setattr(runner, "execute", explode)
    with TestClient(app) as client, client.websocket_connect(STREAM) as ws:
        ws.send_json(hello())
        _receive_until(ws, "replay_complete")
        ws.send_json(command("c1", type="create_thread", thread_id="t1"))
        assert ws.receive_json() == {"type": "error", "message": "command c1 failed on the server"}


def test_live_frames_of_runs_in_followed_threads() -> None:
    app, _ = build(Script(say("Hello there.")))
    with TestClient(app) as client:
        _post(client, "c1", type="create_thread", thread_id="t1")
        with client.websocket_connect(STREAM) as ws:
            ws.send_json(hello(threads=["t1"]))
            _receive_until(ws, "replay_complete")
            ws.send_json(command("c2", type="post_message", thread_id="t1", content="Hi"))
            frames = _until_event(ws, "run_ended")
            live = [f["event"] for f in frames if f["type"] == "live"]
            assert {"type": "text_delta", "part": 0, "delta": "Hello there.", "offset": 0} in live
            types = [f["event"]["type"] for f in frames if f["type"] == "event"]
            assert "run_ended" in types


def test_a_run_resumed_by_an_answer_streams_again() -> None:
    app, _ = build(Script(ask("q1"), say("Tuesday it is.")), ask=True)
    with TestClient(app) as client:
        _post(client, "c1", type="create_thread", thread_id="t1")
        with client.websocket_connect(STREAM) as ws:
            ws.send_json(hello(threads=["t1"]))
            _receive_until(ws, "replay_complete")
            ws.send_json(command("c2", type="post_message", thread_id="t1", content="Plan"))
            [paused] = [f for f in _until_event(ws, "run_paused") if f["type"] == "event"][-1:]
            answer = {"answers": [{"selected": ["Tuesday"]}]}
            run = paused["event"]["run_id"]
            ws.send_json(
                command("c3", type="answer_deferred", run_id=run, tool_call_id="q1", answer=answer)
            )
            frames = _until_event(ws, "run_ended")
            live = [f["event"] for f in frames if f["type"] == "live"]
            assert {"type": "text_delta", "part": 0, "delta": "Tuesday it is.", "offset": 0} in live


def test_every_turn_of_a_run_that_pauses_again_and_again_streams_once() -> None:
    def turn(step: int) -> ModelResponse:
        asked = ask(f"q{step}").parts
        return ModelResponse(parts=[TextPart(f"Step {step}."), *asked])

    app, _ = build(Script(*[turn(step) for step in range(5)], say("Done.")), ask=True)
    with TestClient(app) as client:
        _post(client, "c1", type="create_thread", thread_id="t1")
        with client.websocket_connect(STREAM) as ws:
            ws.send_json(hello(threads=["t1"]))
            _receive_until(ws, "replay_complete")
            ws.send_json(command("c", type="post_message", thread_id="t1", content="Plan"))
            said: list[str] = []
            for step in range(5):
                frames = _until_event(ws, "run_paused")
                said += [
                    f["event"]["delta"]
                    for f in frames
                    if f["type"] == "live" and f["event"]["type"] == "text_delta"
                ]
                run = next(
                    f for f in frames if f["type"] == "event" and f["event"]["type"] == "run_paused"
                )["event"]["run_id"]
                answer = {"reply": "Go on"}
                ws.send_json(
                    command(
                        f"a{step}",
                        type="answer_deferred",
                        run_id=run,
                        tool_call_id=f"q{step}",
                        answer=answer,
                    )
                )
            frames = _until_event(ws, "run_ended")
            said += [
                f["event"]["delta"]
                for f in frames
                if f["type"] == "live" and f["event"]["type"] == "text_delta"
            ]
            assert said == [f"Step {step}." for step in range(5)] + ["Done."]


def test_runs_in_progress_are_listed_and_watched() -> None:
    latch = Latch()
    app, _ = build(Script(call("hold"), say("Released.")), latch=latch)
    with TestClient(app) as client:
        _post(client, "c1", type="create_thread", thread_id="t1")
        _post(client, "c2", type="post_message", thread_id="t1", content="Go")
        wait_for(latch.entered.is_set)
        with client.websocket_connect(STREAM) as ws:
            ws.send_json(hello(threads=["t1"]))
            welcome = ws.receive_json()
            [active] = welcome["active_runs"]
            assert active["thread_id"] == "t1"
            assert active["started_at"] is not None, "when its turn started, for a client's clock"
            ws.send_json(command("c3", type="watch_run", run_id=active["run_id"]))
            latch.released.set()
            frames = _until_event(ws, "run_ended")
            assert [f["ok"] for f in frames if f["type"] == "command_result"] == [True]
            deltas = [f["event"] for f in frames if f["type"] == "live"]
            assert {"type": "text_delta", "part": 0, "delta": "Released.", "offset": 0} in deltas


def test_a_run_running_as_a_client_joins_is_streamed_once_though_its_start_follows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    latch = Latch()
    app, _ = build(Script(call("hold"), say("Released.")), latch=latch)

    async def before_the_start(self: Workspace) -> int:
        return 2  # the head as read just before the run's run_started, seq 3, was written

    with TestClient(app) as client:
        _post(client, "c1", type="create_thread", thread_id="t1")
        _post(client, "c2", type="post_message", thread_id="t1", content="Go")
        wait_for(latch.entered.is_set)
        monkeypatch.setattr(Workspace, "head_seq", before_the_start)
        with client.websocket_connect(STREAM) as ws:
            ws.send_json(hello(threads=["t1"]))
            assert len(ws.receive_json()["active_runs"]) == 1, "listed as running"
            latch.released.set()
            frames = _until_event(ws, "run_ended")
            started = [
                f for f in frames if f["type"] == "event" and f["event"]["type"] == "run_started"
            ]
            assert [f["seq"] for f in started] == [3], "and its start follows the head"
            deltas = [
                f["event"]["delta"]
                for f in frames
                if f["type"] == "live" and f["event"]["type"] == "text_delta"
            ]
            assert deltas == ["Released."], "streamed once"


def test_a_client_from_the_head_still_watches_runs_in_progress() -> None:
    latch = Latch()
    app, _ = build(Script(call("hold"), say("Released.")), latch=latch)
    with TestClient(app) as client:
        _post(client, "c1", type="create_thread", thread_id="t1")
        _post(client, "c2", type="post_message", thread_id="t1", content="Go")
        wait_for(latch.entered.is_set)
        with client.websocket_connect(STREAM) as ws:
            ws.send_json(hello(from_head=True, threads=["t1"]))
            welcome = ws.receive_json()
            [active] = welcome["active_runs"]
            assert active["thread_id"] == "t1"
            latch.released.set()
            frames = _until_event(ws, "run_ended")
            head = welcome["head_seq"]
            assert frames[0] == {"type": "replay_complete", "up_to_seq": head}, "nothing replayed"
            deltas = [f["event"] for f in frames if f["type"] == "live"]
            assert {"type": "text_delta", "part": 0, "delta": "Released.", "offset": 0} in deltas


def test_only_runs_in_followed_threads_are_watched() -> None:
    latch = Latch()
    app, _ = build(Script(call("hold"), say("Released.")), latch=latch)
    with TestClient(app) as client:
        _post(client, "c1", type="create_thread", thread_id="t1")
        _post(client, "c2", type="create_thread", thread_id="t2")
        _post(client, "c3", type="post_message", thread_id="t1", content="Go")
        wait_for(latch.entered.is_set)
        with client.websocket_connect(STREAM) as ws:
            ws.send_json(hello(threads=["t2"]))
            [active] = ws.receive_json()["active_runs"]
            assert active["thread_id"] == "t1", "every running run is listed"
            _receive_until(ws, "replay_complete")
            latch.released.set()
            wait_for(lambda: _runs_ended(client) == 1)
            _post(client, "c4", type="set_thread_mode", thread_id="t2", mode="suggest")
            frames = _until_event(ws, "thread_mode_changed")
    assert [f["type"] for f in frames] == ["event"], "no live frames from t1's run"


def test_replayed_runs_are_not_watched(monkeypatch: pytest.MonkeyPatch) -> None:
    app, runner = build(Script(say("Hi.")))
    watched: list[str] = []
    watch = runner.watch
    monkeypatch.setattr(runner, "watch", lambda run_id: watched.append(run_id) or watch(run_id))
    with TestClient(app) as client:
        _post(client, "c1", type="create_thread", thread_id="t1")
        _post(client, "c2", type="post_message", thread_id="t1", content="Hi")
        wait_for(lambda: _runs_ended(client) == 1)
        with client.websocket_connect(STREAM) as ws:
            ws.send_json(hello(threads=["t1"]))
            replayed = _receive_until(ws, "replay_complete")
            assert "run_started" in [f["event"]["type"] for f in replayed if f["type"] == "event"]
            ws.send_json(command("c3", type="set_thread_mode", thread_id="t1", mode="suggest"))
            _until_event(ws, "thread_mode_changed")
    assert watched == [], "an ended run in the replay is not watched"


def test_a_runs_buffered_frames_beyond_the_outbox_do_not_disconnect_the_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run watched mid-turn replays its buffer at once, which may exceed the outbox."""
    latch = Latch()
    app, runner = build(Script(call("hold"), say("Done.")), latch=latch, outbox_size=10)
    buffered = [LiveFrame(run_id="r", event=TextDelta(part=0, delta=str(n))) for n in range(50)]

    async def watch(run_id: str) -> AsyncIterator[LiveFrame]:
        for frame in buffered:
            yield frame.model_copy(update={"run_id": run_id})

    monkeypatch.setattr(runner, "watch", watch)
    with TestClient(app) as client:
        _post(client, "c1", type="create_thread", thread_id="t1")
        _post(client, "c2", type="post_message", thread_id="t1", content="Go")
        wait_for(latch.entered.is_set)
        with client.websocket_connect(STREAM) as ws:
            ws.send_json(hello(threads=["t1"]))
            frames: list[dict[str, Any]] = []
            for _ in range(200):  # a regression fails here, rather than hanging
                if sum(f["type"] == "live" for f in frames) == len(buffered):
                    break
                frames.append(ws.receive_json())
            latch.released.set()
    deltas = [f["event"]["delta"] for f in frames if f["type"] == "live"]
    assert deltas == [str(n) for n in range(50)]


def _bare_stream(outbox_size: int) -> stream.Stream:
    """A connection with nothing behind it, to drive its outbox by hand."""
    return stream.Stream(
        Mock(),
        "w1",
        open_workspace=Mock(),
        runner=Mock(),
        hello_timeout=1.0,
        outbox_size=outbox_size,
        telemetry=Mock(),
    )


def _delta(n: int = 0) -> LiveFrame:
    return LiveFrame(run_id="r", event=TextDelta(part=0, delta=str(n)))


async def test_thinking_is_shed_first_when_the_client_falls_behind() -> None:
    connection = _bare_stream(10)
    thought = LiveFrame(run_id="r", event=ThinkingDelta(part=1, delta="hm"))
    frames = [_delta(0), thought, _delta(1), _delta(2), _delta(3), _delta(4), thought, _delta(5)]

    async def watch(run_id: str) -> AsyncIterator[LiveFrame]:
        for frame in frames:
            yield frame

    connection._runner.watch = watch
    workspace = Mock()
    workspace.hidden = AsyncMock(return_value=SimpleNamespace(threads=set()))
    connection._watch(workspace, "r", "t1")
    for _ in range(20):
        await asyncio.sleep(0)
    sent = [connection._outbox.get_nowait() for _ in range(connection._outbox.qsize())]
    assert [f["event"]["type"] for f in map(json.loads, sent)] == [
        "text_delta",
        "thinking_delta",
        *["text_delta"] * 4,
        "text_delta",
    ], "the second thought found the outbox more than half full, and was dropped; text never is"


async def test_live_frames_leave_the_outbox_room_for_events_and_results() -> None:
    connection = _bare_stream(10)
    forwarders = [asyncio.create_task(connection._put_waiting(_delta(n))) for n in range(30)]
    await asyncio.sleep(0)
    assert connection._outbox.qsize() == 9, "live frames stop short of the reserve"
    connection._put(ErrorFrame(message="an event or a result"))
    assert connection._outbox.qsize() == 10
    assert not connection._overflowed, "the burst took no room from them"
    for forwarder in forwarders:
        forwarder.cancel()


async def test_a_live_frame_that_finds_no_room_for_long_closes_the_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stream, "LIVE_WAIT", 0.01)
    connection = _bare_stream(10)
    for n in range(9):
        await connection._put_waiting(_delta(n))
    assert not connection._overflowed
    await connection._put_waiting(_delta(9))  # nothing is taking frames
    assert connection._overflowed, "a client that never makes room is closed (4429)"
    assert connection._outbox.qsize() == 9


async def test_a_forwarder_waiting_for_room_is_cancelled_cleanly() -> None:
    connection = _bare_stream(10)
    for n in range(9):
        await connection._put_waiting(_delta(n))
    waiting = asyncio.create_task(connection._put_waiting(_delta(9)))
    await asyncio.sleep(0)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert connection._outbox.qsize() == 9
    assert not connection._overflowed
    connection._outbox.get_nowait()
    connection._room.set()
    await asyncio.wait_for(connection._put_waiting(_delta(10)), 1)
    assert connection._outbox.qsize() == 9


def _runs_ended(client: TestClient) -> int:
    log = client.get("/v1/workspaces/w1/events").json()
    return sum(envelope["event"]["type"] == "run_ended" for envelope in log)


def test_a_client_that_cannot_keep_up_is_disconnected() -> None:
    app, _ = build(Script(), outbox_size=1)
    with TestClient(app) as client:
        for n in range(30):
            _post(client, f"c{n}", type="create_thread", thread_id=f"t{n}")
        with client.websocket_connect(STREAM) as ws:
            ws.send_json(hello())
            with pytest.raises(WebSocketDisconnect) as closed:
                _drain(ws)
            assert closed.value.code == 4429


def _drain(ws: WebSocketTestSession) -> None:
    for _ in range(100):
        ws.receive_json()


async def _hide_t2_from_bob(
    tenant_id: TenantId, workspace_id: WorkspaceId, actor: Actor
) -> Visibility:
    return Visibility(threads=frozenset({"t2"} if actor.participant == "user:bob" else ()))


def test_replay_ends_at_the_head_whatever_is_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stream, "REPLAY_PAGE", 1)
    app, _ = build(Script(), hidden=_hide_t2_from_bob)
    with TestClient(app) as client:
        for n, thread in enumerate(("t1", "t3", "t2")):
            _post(client, f"c{n}", type="create_thread", thread_id=thread)
        with client.websocket_connect(STREAM, headers={"x-user": "bob"}) as ws:
            ws.send_json(hello())
            assert ws.receive_json()["head_seq"] == 3
            replayed = _receive_until(ws, "replay_complete")
            assert [f.get("seq") for f in replayed] == [1, 2, None], "t2's is hidden"
            _post(client, "c4", type="set_thread_mode", thread_id="t2", mode="suggest")
            _post(client, "c5", type="set_thread_mode", thread_id="t1", mode="suggest")
            live = ws.receive_json()
            assert (live["seq"], live["thread_id"]) == (5, "t1")


class Hider:
    """Hides t1 from Bob once told to."""

    def __init__(self) -> None:
        self.hiding = False

    async def __call__(
        self, tenant_id: TenantId, workspace_id: WorkspaceId, actor: Actor
    ) -> Visibility:
        hides = self.hiding and actor.participant == "user:bob"
        return Visibility(threads=frozenset({"t1"} if hides else ()))


def test_a_watched_run_stops_once_its_thread_is_hidden() -> None:
    latch, hider = Latch(), Hider()
    script = Script(call("hold"), say("Released."))
    app, _ = build(script, latch=latch, hidden=hider, hidden_refresh=timedelta(0))
    with TestClient(app) as client:
        _post(client, "c1", type="create_thread", thread_id="t1")
        _post(client, "c2", type="post_message", thread_id="t1", content="Go")
        wait_for(latch.entered.is_set)
        with client.websocket_connect(STREAM, headers={"x-user": "bob"}) as ws:
            ws.send_json(hello())
            [active] = ws.receive_json()["active_runs"]
            _receive_until(ws, "replay_complete")
            ws.send_json(command("c3", type="watch_run", run_id=active["run_id"]))
            assert _receive_until(ws, "command_result")[-1]["ok"]
            hider.hiding = True
            latch.released.set()
            wait_for(lambda: _runs_ended(client) == 1)
            _post(client, "c4", type="create_thread", thread_id="t2")
            frames = _until_event(ws, "thread_created")
            assert [f["type"] for f in frames] == ["event"], "nothing of t1's run"
            assert frames[-1]["thread_id"] == "t2"


ALICE = UserActor(id="alice")


async def test_a_runs_latest_start_is_read_back_a_page_at_a_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = await Workspaces(InMemoryStorage()).open("acme", "w", actor=ALICE)
    thread = await ws.create_thread()
    agent = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_1"))
    started = await agent.record(RunStarted(run_id="run_1", thread_id=thread.id))
    for text in ("after", "the", "start"):
        await ws.post_message(thread.id, text)
    monkeypatch.setattr(stream, "_PAGE", 1)
    seq, at = await stream._started(ws, "run_1", thread.id)
    assert (seq, at) == (started.seq, (await ws.read())[seq - 1].ts)
    assert await stream._started(ws, "run_none", thread.id) == (0, None)
