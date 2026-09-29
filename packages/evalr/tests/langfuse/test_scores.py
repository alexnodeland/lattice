from collections.abc import Iterator, Sequence
from datetime import UTC, datetime

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
                trace_id=body.get("traceId"),
                session_id=body.get("sessionId"),
                evaluator=body["metadata"].get("evaluator"),
                version=body["metadata"].get("version"),
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
    assert "sessionId" not in arrived["helpfulness.rating"]


async def test_feedback_arrives_on_its_session_when_it_was_given(
    client: Langfuse, server: FakeLangfuse
) -> None:
    given = datetime(2026, 9, 29, 12, 30, tzinfo=UTC)
    feedback = Score(
        id="7b0f3c52-1f0e-5b8a-9d4c-2a6e8f1b3c5d",
        name="helpfulness.resolved",
        value=False,
        data_type="BOOLEAN",
        session_id="thread-1",
        timestamp=given,
        source={"tenant_id": "acme", "actor": "alice"},
    )
    sink = LangfuseScoreSink(client)
    await sink.record([feedback])
    await sink.flush()
    body = server.scores[feedback.id]
    assert (body["sessionId"], body["value"], body["dataType"]) == ("thread-1", 0.0, "BOOLEAN")
    assert "traceId" not in body
    assert body["metadata"] == {"tenant_id": "acme", "actor": "alice"}
    assert datetime.fromisoformat(server.score_times[feedback.id]) == given


async def test_scores_need_a_trace_or_a_session(client: Langfuse) -> None:
    untraced = Verdict(value=Helpfulness(rating=1, resolved=False), evaluator="e", version="1")
    with pytest.raises(ValueError, match="to traces or sessions"):
        await LangfuseScoreSink(client).record(scores(untraced, subject="s"))
