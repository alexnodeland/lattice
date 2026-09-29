from collections.abc import Sequence
from typing import Any

from opentelemetry import trace

from evalr.contracts import check_score_sink
from evalr.core import Score, Verdict, scores
from evalr.online import EVALUATION_RESULT, OtelEventSink

from ..decision.models import Helpfulness
from .logs import logs

TRACE = "0af7651916cd43dd8448eb211c80319c"
SPAN = "b7ad6b7169203331"


def verdict() -> Verdict[Helpfulness]:
    return Verdict(
        value=Helpfulness(rating=4, resolved=True, category="bug", reason="refunded quickly"),
        confidence={"rating": 0.9},
        evaluator="judge",
        version="2",
    )


async def test_each_score_is_an_evaluation_result_event_on_the_judged_span() -> None:
    with logs() as kept:
        await OtelEventSink(kept.provider).record(
            scores(verdict(), trace_id=TRACE, span_id=SPAN, subject="turn-1")
        )
        events = kept.records()
    assert {e.log_record.event_name for e in events} == {EVALUATION_RESULT}
    assert {(e.log_record.trace_id, e.log_record.span_id) for e in events} == {
        (int(TRACE, 16), int(SPAN, 16))
    }
    attributes = {
        str(dict(e.log_record.attributes or {})["gen_ai.evaluation.name"]): dict(
            e.log_record.attributes or {}
        )
        for e in events
    }
    assert set(attributes) == {
        "helpfulness.rating",
        "helpfulness.resolved",
        "helpfulness.category",
        "helpfulness.share",
        "helpfulness.reason",
    }
    reason = attributes["helpfulness.reason"]
    assert reason["gen_ai.evaluation.explanation"] == "refunded quickly"
    assert "gen_ai.evaluation.score.value" not in reason
    assert "gen_ai.evaluation.score.label" not in reason
    rating = attributes["helpfulness.rating"]
    assert rating["gen_ai.evaluation.score.value"] == 4.0
    assert rating["gen_ai.evaluation.explanation"] == "reason: refunded quickly"
    assert rating["evalr.confidence"] == 0.9
    assert (rating["evalr.evaluator.name"], rating["evalr.evaluator.version"]) == ("judge", "2")
    resolved = attributes["helpfulness.resolved"]
    assert (
        resolved["gen_ai.evaluation.score.value"],
        resolved["gen_ai.evaluation.score.label"],
    ) == (1.0, "true")
    assert attributes["helpfulness.category"]["gen_ai.evaluation.score.label"] == "bug"
    assert "evalr.confidence" not in attributes["helpfulness.category"]


async def test_a_no_is_zero_and_a_verdict_without_text_has_no_explanation() -> None:
    no = Verdict(value=Helpfulness(rating=1, resolved=False), evaluator="e", version="1")
    with logs() as kept:
        await OtelEventSink(kept.provider).record(scores(no, subject="s"))
        events = {
            str(dict(e.log_record.attributes or {})["gen_ai.evaluation.name"]): e
            for e in kept.records()
        }
    resolved = dict(events["helpfulness.resolved"].log_record.attributes or {})
    assert (
        resolved["gen_ai.evaluation.score.value"],
        resolved["gen_ai.evaluation.score.label"],
    ) == (0.0, "false")
    assert "gen_ai.evaluation.explanation" not in resolved
    assert not events["helpfulness.resolved"].log_record.trace_id


async def test_without_a_trace_of_its_own_a_score_takes_the_current_span() -> None:
    no = Verdict(value=Helpfulness(rating=1, resolved=False), evaluator="e", version="1")
    parent = trace.NonRecordingSpan(
        trace.SpanContext(
            trace_id=int(TRACE, 16),
            span_id=int(SPAN, 16),
            is_remote=False,
            trace_flags=trace.TraceFlags(trace.TraceFlags.SAMPLED),
        )
    )
    with logs() as kept, trace.use_span(parent):
        await OtelEventSink(kept.provider).record(scores(no, subject="s"))
        records = kept.records()
    assert {(r.log_record.trace_id, r.log_record.span_id) for r in records} == {
        (int(TRACE, 16), int(SPAN, 16))
    }


def as_score(attributes: dict[str, Any], trace_id: int) -> Score:
    """An event read back as a score, as a reader of the events would."""
    label = attributes.get("gen_ai.evaluation.score.label")
    number = attributes.get("gen_ai.evaluation.score.value")
    value: bool | float | str
    if label in ("true", "false"):
        value, data_type = label == "true", "BOOLEAN"
    elif label is not None:
        value, data_type = label, "CATEGORICAL"
    elif number is not None:
        value, data_type = number, "NUMERIC"
    else:
        value, data_type = attributes["gen_ai.evaluation.explanation"], "TEXT"
    return Score(
        id=attributes["evalr.score.id"],
        name=attributes["gen_ai.evaluation.name"],
        value=value,
        data_type=data_type,
        trace_id=f"{trace_id:032x}" if trace_id else None,
        evaluator=attributes["evalr.evaluator.name"],
        version=attributes["evalr.evaluator.version"],
    )


async def test_the_sink_meets_the_contract_for_a_reader_keyed_by_score_id() -> None:
    with logs() as kept:

        async def recorded() -> Sequence[Score]:
            latest = {}
            for event in kept.records():
                score = as_score(
                    dict(event.log_record.attributes or {}), event.log_record.trace_id or 0
                )
                latest[score.id] = score
            return list(latest.values())

        await check_score_sink(OtelEventSink(kept.provider), recorded)
