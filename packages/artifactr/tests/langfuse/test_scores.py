"""Langfuse behind the score ports, checked by the same contract as the fakes."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from opentelemetry.sdk.trace import TracerProvider

from artifactr.core import AgentActor, GiveFeedback, RunStarted, TurnTarget, UserActor
from artifactr.langfuse import LangfuseScoreConfigs, LangfuseScores
from artifactr.scores import (
    FeedbackMirror,
    Score,
    ScoreConfig,
    ScoreConfigStore,
    ScoreSink,
    sync_score_configs,
)
from artifactr.workspace import InMemoryStorage, Workspaces
from tests.artifact_types import Accuracy, Helpfulness
from tests.langfuse.conftest import Backend, FakeLangfuseApi
from tests.scores.fakes import FakeConfigStore, FakeSink

TRACE = "4bf92f3577b34da6a3ce929d0e0e4736"
NOW = datetime(2026, 9, 28, tzinfo=UTC)

type Recorded = dict[str, tuple[str, float | str, str | None, str | None]]
"""Scores a backend holds, by id: name, value, trace and session."""


def score(id: str, value: float | str, data_type: Any, **target: Any) -> Score:
    return Score(
        id=id,
        name=f"helpfulness.{id}",
        value=value,
        data_type=data_type,
        trace_id=target.get("trace_id"),
        session_id=target.get("session_id"),
        timestamp=NOW,
        metadata={"tenant_id": "acme"},
    )


@pytest.fixture(params=["fake", "langfuse"])
def sink(
    request: pytest.FixtureRequest, backend: Backend
) -> Iterator[tuple[ScoreSink, Callable[[], Recorded]]]:
    if request.param == "fake":
        fake = FakeSink()
        yield (
            fake,
            lambda: {
                s.id: (s.name, s.value, s.trace_id, s.session_id) for s in fake.scores.values()
            },
        )
        return

    def recorded() -> Recorded:
        backend.client.flush()
        return {
            id: (body["name"], body["value"], body.get("traceId"), body.get("sessionId"))
            for id, body in backend.api.scores.items()
        }

    yield LangfuseScores(backend.client), recorded


async def test_the_score_sink_contract(sink: tuple[ScoreSink, Callable[[], Recorded]]) -> None:
    port, recorded = sink
    await port.send(score("rating", 4.0, "NUMERIC", trace_id=TRACE))
    await port.send(score("useful", 1.0, "BOOLEAN", session_id="thr_1"))
    await port.send(score("tone", "casual", "CATEGORICAL", trace_id=TRACE))
    await port.send(score("reason", "slow", "TEXT", trace_id=TRACE))
    await port.send(score("reason", "too slow", "TEXT", trace_id=TRACE))
    assert recorded() == {
        "rating": ("helpfulness.rating", 4.0, TRACE, None),
        "useful": ("helpfulness.useful", 1.0, None, "thr_1"),
        "tone": ("helpfulness.tone", "casual", TRACE, None),
        "reason": ("helpfulness.reason", "too slow", TRACE, None),
    }


async def test_langfuse_scores_carry_their_type_and_metadata(backend: Backend) -> None:
    await LangfuseScores(backend.client).send(score("rating", 4.0, "NUMERIC", trace_id=TRACE))
    backend.client.flush()
    body = backend.api.scores["rating"]
    assert (body["dataType"], body["metadata"]) == ("NUMERIC", {"tenant_id": "acme"})
    with pytest.raises(ValueError, match="a NUMERIC score cannot be 'four'"):
        await LangfuseScores(backend.client).send(score("rating", "four", "NUMERIC"))


@pytest.fixture(params=["fake", "langfuse"])
def store(request: pytest.FixtureRequest) -> Iterator[ScoreConfigStore]:
    existing = ("helpfulness.rating", "other.a", "other.b")
    if request.param == "fake":
        yield FakeConfigStore(*existing)
        return
    backend = Backend(FakeLangfuseApi(*existing))
    yield LangfuseScoreConfigs(backend.client)
    backend.client.shutdown()


async def test_the_score_config_store_contract(store: ScoreConfigStore) -> None:
    assert set(await store.names()) == {"helpfulness.rating", "other.a", "other.b"}
    created = await sync_score_configs(store, [Helpfulness, Accuracy])
    assert created == [
        "helpfulness.reason",
        "accuracy.correct",
        "accuracy.verdict",
        "accuracy.tone",
        "accuracy.confidence",
    ]
    assert len(set(await store.names())) == 8
    assert await sync_score_configs(store, [Helpfulness, Accuracy]) == []


async def test_langfuse_score_configs_describe_each_field(api: FakeLangfuseApi) -> None:
    backend = Backend(api)
    configs = LangfuseScoreConfigs(backend.client)
    await sync_score_configs(configs, [Accuracy])
    created = {config["name"]: config for config in api.configs}
    assert created["accuracy.verdict"]["categories"] == [
        {"label": "right", "value": 0},
        {"label": "wrong", "value": 1},
    ]
    assert (
        created["accuracy.confidence"]["minValue"],
        created["accuracy.confidence"]["maxValue"],
    ) == (0, 1)
    assert "categories" not in created["accuracy.correct"]
    too_long = ScoreConfig(
        name="a_rather_long_feedback_type.a_long_field",
        feedback_type="a_rather_long_feedback_type",
        field="a_long_field",
        data_type="TEXT",
        description="Explained.",
    )
    with pytest.raises(ValueError, match="shorten"):
        await configs.create(too_long)
    await configs.create(
        ScoreConfig(name="t.f", feedback_type="t", field="f", data_type="TEXT", description="Why")
    )
    assert api.configs[-1]["description"] == "Why"
    backend.client.shutdown()


async def test_feedback_reaches_langfuse_on_its_trace(backend: Backend) -> None:
    workspaces = Workspaces(InMemoryStorage(), tracer_provider=TracerProvider())
    ws = await workspaces.open("acme", "launch", actor=UserActor(id="alice"))
    thread = await ws.create_thread()
    agent = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_1"))
    await agent.record(RunStarted(run_id="run_1", thread_id=thread.id, trace_id=TRACE))
    await ws.commit(
        GiveFeedback(
            feedback_type="helpfulness", target=TurnTarget(run_id="run_1"), value={"rating": 5}
        )
    )
    mirror = FeedbackMirror(ws, LangfuseScores(backend.client))
    [envelope] = await ws.read(after_seq=await ws.head_seq() - 1)
    [sent] = await mirror.mirror(envelope)
    backend.client.flush()
    body = backend.api.scores[sent.id]
    assert (body["name"], body["value"], body["traceId"]) == ("helpfulness.rating", 5.0, TRACE)
