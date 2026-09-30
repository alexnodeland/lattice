"""The feedback mirror: which trace or session each piece of feedback is scored on."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from opentelemetry.sdk.trace import TracerProvider

from artifactr.core import (
    AgentActor,
    ArtifactTarget,
    DeferredRequest,
    Envelope,
    FeedbackGiven,
    GiveFeedback,
    MessageTarget,
    RunEnded,
    RunPaused,
    RunStarted,
    ThreadTarget,
    TurnTarget,
    UserActor,
)
from artifactr.scores import FeedbackMirror, sync_score_configs
from artifactr.workspace import InMemoryStorage, Workspace, Workspaces
from evalr.core import Score
from evalr.memory import InMemoryScoreSink
from tests.artifact_types import Accuracy, Helpfulness, Note
from tests.scores.fakes import seeded

ALICE = UserActor(id="alice")
FIRST = "4bf92f3577b34da6a3ce929d0e0e4736"
SECOND = "0af7651916cd43dd8448eb211c80319c"
RATING: dict[str, Any] = {"rating": 4}
CURSOR = "langfuse"


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
async def ws(storage: InMemoryStorage) -> Workspace:
    traced = Workspaces(storage, tracer_provider=TracerProvider())
    return await traced.open("t1", "w1", actor=ALICE)


async def mirrored(ws: Workspace, sink: InMemoryScoreSink, *, after_seq: int = 0) -> list[Score]:
    mirror = FeedbackMirror(ws, sink, cursor=CURSOR)
    return [s for e in await ws.read(after_seq=after_seq) for s in await mirror.mirror(e)]


async def test_turn_and_message_feedback_is_scored_on_the_runs_latest_trace(
    ws: Workspace,
) -> None:
    thread = await ws.create_thread()
    agent = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_1"))
    question = DeferredRequest(tool_call_id="q1", tool_name="ask_user", kind="question")
    await agent.record(RunStarted(run_id="run_1", thread_id=thread.id, trace_id=FIRST))
    await agent.record(RunPaused(run_id="run_1", thread_id=thread.id, requests=(question,)))
    await agent.record(
        RunStarted(run_id="run_1", thread_id=thread.id, trigger="resume", trace_id=SECOND)
    )
    await agent.record(RunEnded(run_id="run_1", thread_id=thread.id, status="completed"))
    head = await ws.head_seq()
    await ws.commit(
        GiveFeedback(feedback_type="helpfulness", target=TurnTarget(run_id="run_1"), value=RATING)
    )
    message = MessageTarget(message_id="m1", thread_id=thread.id, run_id="run_1")
    await ws.commit(GiveFeedback(feedback_type="helpfulness", target=message, value=RATING))
    sink = InMemoryScoreSink()
    turn, on_message = await mirrored(ws, sink, after_seq=head)
    assert (turn.name, turn.value, turn.data_type) == ("helpfulness.rating", 4.0, "NUMERIC")
    assert (turn.trace_id, turn.session_id) == (SECOND, None), "the attempt that finished"
    assert on_message.trace_id == SECOND
    assert turn.metadata == {
        "tenant_id": "t1",
        "workspace_id": "w1",
        "feedback_type": "helpfulness",
        "target": "turn",
        "actor": "user:alice",
        "actor_kind": "user",
        "seq": str(head + 1),
    }


async def test_without_a_trace_feedback_is_scored_on_the_session(ws: Workspace) -> None:
    thread = await ws.create_thread()
    agent = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_2"))
    await agent.record(RunStarted(run_id="run_2", thread_id=thread.id))
    for target in (
        TurnTarget(run_id="run_2"),
        ThreadTarget(thread_id=thread.id),
        MessageTarget(message_id="m1", thread_id=thread.id),
    ):
        feedback = {"rating": 2, "reason": "slow"}
        await ws.commit(GiveFeedback(feedback_type="helpfulness", target=target, value=feedback))
    scores = await mirrored(ws, InMemoryScoreSink())
    assert len(scores) == 6
    assert {(s.trace_id, s.session_id) for s in scores} == {(None, thread.id)}
    assert {s.name for s in scores} == {"helpfulness.rating", "helpfulness.reason"}


async def test_artifact_feedback_is_scored_on_the_trace_of_the_version(
    ws: Workspace, storage: InMemoryStorage
) -> None:
    thread = await ws.create_thread()
    agent = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_1"))
    await agent.record(RunStarted(run_id="run_1", thread_id=thread.id))
    await agent.create(Note(text="draft"), artifact_id="n1", thread_id=thread.id)
    untraced = await Workspaces(storage).open("t1", "w1", actor=ALICE)
    await untraced.create(Note(text="mine"), artifact_id="n2")
    by_agent = await untraced.as_actor(agent.actor).create(Note(text="late"), artifact_id="n3")
    assert by_agent
    for artifact_id in ("n1", "n2", "n3"):
        target = ArtifactTarget(artifact_id=artifact_id, version=1)
        await ws.commit(GiveFeedback(feedback_type="accuracy", target=target, value={"correct": 1}))
    scores = await mirrored(ws, InMemoryScoreSink())
    [revision] = await ws.revisions("n1")
    assert revision.trace_id is not None
    on_draft = [s for s in scores if s.trace_id == revision.trace_id]
    assert [s.name for s in on_draft] == [
        "accuracy.correct",
        "accuracy.verdict",
        "accuracy.tone",
        "accuracy.confidence",
    ]
    on_late = [s for s in scores if s.trace_id is None]
    assert {s.session_id for s in on_late} == {thread.id}, "the agent's thread, untraced"
    assert len(scores) == 8, "a person's untraced version has nowhere to go"


async def test_mirroring_again_replaces_scores(ws: Workspace) -> None:
    thread = await ws.create_thread()
    await ws.commit(
        GiveFeedback(
            feedback_type="helpfulness", target=ThreadTarget(thread_id=thread.id), value=RATING
        )
    )
    sink = InMemoryScoreSink()
    first = await mirrored(ws, sink)
    second = await mirrored(ws, sink)
    assert [s.id for s in first] == [s.id for s in second]
    assert len(sink.scores) == 1


async def test_types_this_process_does_not_know_are_skipped(ws: Workspace) -> None:
    unknown = Envelope(
        seq=1,
        id="e1",
        ts=datetime.now(UTC),
        workspace_id="w1",
        actor=ALICE,
        event=FeedbackGiven(
            feedback_type="retired", target=ThreadTarget(thread_id="thr_1"), value={}
        ),
    )
    assert await FeedbackMirror(ws, InMemoryScoreSink(), cursor=CURSOR).scores(unknown) == []


async def test_a_timestamp_without_a_time_zone_is_taken_as_utc(ws: Workspace) -> None:
    given = datetime(2026, 9, 29, 9, 30)
    envelope = Envelope(
        seq=1,
        id="e1",
        ts=given,
        workspace_id="w1",
        actor=ALICE,
        event=FeedbackGiven(
            feedback_type="helpfulness", target=ThreadTarget(thread_id="thr_1"), value=RATING
        ),
    )
    [score] = await FeedbackMirror(ws, InMemoryScoreSink(), cursor=CURSOR).scores(envelope)
    assert score.timestamp == given.replace(tzinfo=UTC)


async def test_following_the_log(ws: Workspace) -> None:
    thread = await ws.create_thread()
    sink = InMemoryScoreSink()
    follower = asyncio.create_task(FeedbackMirror(ws, sink, cursor=CURSOR).follow())
    await ws.commit(
        GiveFeedback(
            feedback_type="helpfulness", target=ThreadTarget(thread_id=thread.id), value=RATING
        )
    )
    for _ in range(100):
        if sink.scores:
            break
        await asyncio.sleep(0.01)
    follower.cancel()
    with pytest.raises(asyncio.CancelledError):
        await follower
    assert [s.name for s in sink.scores.values()] == ["helpfulness.rating"]


async def following(
    mirror: FeedbackMirror, done: Callable[[], Awaitable[bool]], **options: Any
) -> None:
    """Follow the log until ``done``, then stop, as a restarting application would."""
    follower = asyncio.create_task(mirror.follow(**options))
    for _ in range(200):
        if await done():
            break
        await asyncio.sleep(0.01)
    follower.cancel()
    with pytest.raises(asyncio.CancelledError):
        await follower
    assert await done()


async def rate(ws: Workspace, thread_id: str, stars: int) -> int:
    await ws.commit(
        GiveFeedback(
            feedback_type="helpfulness",
            target=ThreadTarget(thread_id=thread_id),
            value={"rating": stars},
        )
    )
    return await ws.head_seq()


async def test_a_restarted_mirror_carries_on_after_its_cursor(ws: Workspace) -> None:
    thread = await ws.create_thread()
    first = await rate(ws, thread.id, 4)
    before = InMemoryScoreSink()

    async def recorded_first() -> bool:
        return await ws.cursor(CURSOR) == first

    await following(FeedbackMirror(ws, before, cursor=CURSOR), recorded_first)
    assert len(before.scores) == 1
    second = await rate(ws, thread.id, 2)
    after = InMemoryScoreSink()

    async def recorded_second() -> bool:
        return await ws.cursor(CURSOR) == second

    await following(FeedbackMirror(ws, after, cursor=CURSOR), recorded_second)
    assert [s.value for s in after.scores.values()] == [2.0], "the first is not sent again"


async def test_the_cursor_is_saved_now_and_then_without_feedback(
    ws: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("artifactr.scores.mirror.SAVE_EVERY", 3)
    for _ in range(7):
        await ws.create_thread()

    async def saved_twice() -> bool:
        return await ws.cursor(CURSOR) == 6

    await following(FeedbackMirror(ws, InMemoryScoreSink(), cursor=CURSOR), saved_twice)


async def test_each_mirror_of_a_workspace_has_its_own_cursor(ws: Workspace) -> None:
    thread = await ws.create_thread()
    head = await rate(ws, thread.id, 4)

    async def warehouse_is_done() -> bool:
        return await ws.cursor("warehouse") == head

    await following(FeedbackMirror(ws, InMemoryScoreSink(), cursor="warehouse"), warehouse_is_done)
    assert await ws.cursor(CURSOR) == 0


async def test_a_mirror_without_a_cursor_starts_over(ws: Workspace) -> None:
    thread = await ws.create_thread()
    await rate(ws, thread.id, 4)
    for _ in range(2):
        sink = InMemoryScoreSink()

        async def recorded(sink: InMemoryScoreSink = sink) -> bool:
            return bool(sink.scores)

        await following(FeedbackMirror(ws, sink, cursor=None), recorded)
    assert await ws.cursor(CURSOR) == 0


async def test_mirroring_again_from_the_start_leaves_the_cursor(ws: Workspace) -> None:
    thread = await ws.create_thread()
    first = await rate(ws, thread.id, 4)
    await ws.save_cursor(CURSOR, first + 5)  # as if another process had got further
    sink = InMemoryScoreSink()

    async def recorded() -> bool:
        return bool(sink.scores)

    await following(FeedbackMirror(ws, sink, cursor=CURSOR), recorded, after_seq=0)
    assert await ws.cursor(CURSOR) == first + 5


async def test_score_configs_are_created_once() -> None:
    store = seeded("helpfulness.rating")
    created = await sync_score_configs(store, [Helpfulness, Accuracy])
    assert created == [
        "helpfulness.reason",
        "accuracy.correct",
        "accuracy.verdict",
        "accuracy.tone",
        "accuracy.confidence",
    ]
    assert await sync_score_configs(store, [Helpfulness, Accuracy]) == []
    everything = await sync_score_configs(store)
    assert "helpfulness.reason" not in everything
    assert await sync_score_configs(store) == []
