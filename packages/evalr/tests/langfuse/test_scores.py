from collections.abc import Iterator, Sequence
from datetime import datetime

import pytest
from langfuse import Langfuse

from evalr.contracts import check_score_config_store, check_score_sink
from evalr.core import Score, ScoreConfig, Verdict, score_configs, scores
from evalr.langfuse import LangfuseScoreConfigStore, LangfuseScoreSink

from ..decision.models import Helpfulness
from .server import FakeLangfuse, connected


@pytest.fixture
def server() -> FakeLangfuse:
    return FakeLangfuse()


@pytest.fixture
def client(server: FakeLangfuse) -> Iterator[Langfuse]:
    with connected(server) as (client, _):
        yield client


def received(server: FakeLangfuse) -> list[Score]:
    """The scores the fake received, as evalr's scores."""
    held: list[Score] = []
    for body in server.scores.values():
        source = dict(body["metadata"])
        evaluator = source.pop("evaluator", None)
        version = source.pop("version", None)
        confidence = source.pop("confidence", None)
        held.append(
            Score(
                id=body["id"],
                name=body["name"],
                value=body["value"] == 1 if body["dataType"] == "BOOLEAN" else body["value"],
                data_type=body["dataType"],
                trace_id=body.get("traceId"),
                span_id=body.get("observationId"),
                session_id=body.get("sessionId"),
                timestamp=datetime.fromisoformat(server.score_times[body["id"]]),
                evaluator=evaluator,
                version=version,
                confidence=confidence,
                source=source,
            )
        )
    return held


async def test_the_sink_meets_the_contract(client: Langfuse, server: FakeLangfuse) -> None:
    sink = LangfuseScoreSink(client)

    async def recorded() -> Sequence[Score]:
        await sink.flush()
        return received(server)

    await check_score_sink(sink, recorded)


async def test_every_kind_of_score_arrives_typed(client: Langfuse, server: FakeLangfuse) -> None:
    verdict = Verdict(
        value=Helpfulness(rating=4, resolved=True, category="bug", reason="refunded"),
        confidence={"rating": 0.9},
        evaluator="judge",
        version="1",
        trace_id="0af7651916cd43dd8448eb211c80319c",
    )
    sink = LangfuseScoreSink(client)
    await sink.record(scores(verdict))
    await sink.flush()
    arrived = {body["name"]: body for body in server.scores.values()}
    assert {n: (b["value"], b["dataType"]) for n, b in arrived.items()} == {
        "helpfulness.rating": (4.0, "NUMERIC"),
        "helpfulness.resolved": (1.0, "BOOLEAN"),
        "helpfulness.category": ("bug", "CATEGORICAL"),
        "helpfulness.share": (0.5, "NUMERIC"),
        "helpfulness.reason": ("refunded", "TEXT"),
    }
    assert arrived["helpfulness.rating"]["metadata"] == {
        "evaluator": "judge",
        "version": "1",
        "confidence": 0.9,
    }
    assert "sessionId" not in arrived["helpfulness.rating"]


async def test_scores_need_a_trace_or_a_session(client: Langfuse, server: FakeLangfuse) -> None:
    untraced = Verdict(value=Helpfulness(rating=1, resolved=False), evaluator="e", version="1")
    sink = LangfuseScoreSink(client)
    with pytest.raises(ValueError, match="to traces or sessions"):
        await sink.record(scores(untraced, subject="s"))
    await sink.flush()
    assert server.scores == {}


async def test_the_config_store_meets_the_contract(client: Langfuse) -> None:
    await check_score_config_store(LangfuseScoreConfigStore(client))


async def test_configs_arrive_with_their_bounds_choices_and_description(
    client: Langfuse, server: FakeLangfuse
) -> None:
    store = LangfuseScoreConfigStore(client)
    for config in score_configs(Helpfulness):
        await store.create(config)
    created = {config["name"]: config for config in server.configs}
    rating = created["helpfulness.rating"]
    assert (rating["dataType"], rating["minValue"], rating["maxValue"]) == ("NUMERIC", 1, 5)
    assert rating["description"] == "How much the reply helped"
    assert created["helpfulness.category"]["categories"] == [
        {"label": "billing", "value": 0},
        {"label": "bug", "value": 1},
        {"label": "other", "value": 2},
    ]
    assert not {"categories", "minValue", "maxValue", "description"} & set(
        created["helpfulness.reason"]
    )


async def test_names_are_read_from_every_page(client: Langfuse, server: FakeLangfuse) -> None:
    for i in range(150):
        server.create_config({"name": f"seeded.{i}", "dataType": "NUMERIC"})
    assert await LangfuseScoreConfigStore(client).names() == {f"seeded.{i}" for i in range(150)}


async def test_a_name_langfuse_refuses_is_not_sent(client: Langfuse, server: FakeLangfuse) -> None:
    too_long = ScoreConfig(
        name="a_rather_long_feedback_type.a_long_field",
        type_name="a_rather_long_feedback_type",
        field="a_long_field",
        data_type="TEXT",
    )
    with pytest.raises(ValueError, match="35 characters at most"):
        await LangfuseScoreConfigStore(client).create(too_long)
    assert server.configs == []
