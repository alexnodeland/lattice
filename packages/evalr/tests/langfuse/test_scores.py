from collections.abc import Iterator, Sequence

import pytest
from langfuse import Langfuse

from evalr.contracts import check_score_sink
from evalr.core import Score, Verdict, scores
from evalr.langfuse import LangfuseScoreSink

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
        value = body["value"]
        if body["dataType"] == "BOOLEAN":
            value = value == 1.0
        held.append(
            Score(
                id=body["id"],
                name=body["name"],
                value=value,
                data_type=body["dataType"],
                trace_id=body["traceId"],
                evaluator=body["metadata"]["evaluator"],
                version=body["metadata"]["version"],
                confidence=body["metadata"].get("confidence"),
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


async def test_scores_need_a_trace(client: Langfuse) -> None:
    untraced = Verdict(value=Helpfulness(rating=1, resolved=False), evaluator="e", version="1")
    with pytest.raises(ValueError, match="attaches scores to traces"):
        await LangfuseScoreSink(client).record(scores(untraced, subject="s"))
