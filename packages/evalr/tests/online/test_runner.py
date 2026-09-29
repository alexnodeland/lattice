from collections.abc import Sequence

import pytest
from opentelemetry import trace

from evalr.core import FunctionEvaluator, HandOff, Score, split_bucket
from evalr.memory import InMemoryScoreSink
from evalr.online import Budget, OnlineEvaluation

from ..conftest import Spans
from ..core.models import Helpfulness, Thread

THREAD = Thread(messages=["hi", "thanks"])


def judge(thread: Thread) -> Helpfulness:
    return Helpfulness(rating=len(thread.messages), resolved=True, reason="fine")


def evaluator(spans: Spans | None = None) -> FunctionEvaluator[Thread, Helpfulness]:
    return FunctionEvaluator(
        judge, verdict_type=Helpfulness, tracer_provider=spans.provider if spans else None
    )


def declining(thread: Thread) -> Helpfulness:
    raise HandOff("unsure")


def failing(thread: Thread) -> Helpfulness:
    raise RuntimeError("down")


class BrokenSink:
    async def record(self, scores: Sequence[Score], /) -> None:
        raise ConnectionError("unreachable")


def test_sampling_is_by_key() -> None:
    online = OnlineEvaluation([evaluator()], sample_rate=0.5, salt="s")
    keys = [f"turn-{i}" for i in range(200)]
    chosen = [k for k in keys if online.sampled(k)]
    assert chosen == [k for k in keys if split_bucket(k, "s") < 0.5]
    assert 60 < len(chosen) < 140
    assert all(OnlineEvaluation([evaluator()]).sampled(k) for k in keys)
    assert not any(OnlineEvaluation([evaluator()], sample_rate=0.0).sampled(k) for k in keys)


async def test_an_input_not_sampled_is_not_judged() -> None:
    sink = InMemoryScoreSink()
    result = await OnlineEvaluation([evaluator()], sample_rate=0.0, sinks=[sink]).judge(
        THREAD, key="turn-1"
    )
    assert (result.sampled, result.verdicts, sink.scores) == (False, (), {})


async def test_verdicts_are_recorded_on_the_judged_span(spans: Spans) -> None:
    sink = InMemoryScoreSink()
    online = OnlineEvaluation([evaluator(spans)], sinks=[sink], type_names={Helpfulness: "helpful"})
    tracer = spans.provider.get_tracer("app")
    with tracer.start_as_current_span("invoke_workflow turn") as turn:
        result = await online.judge(THREAD, key="turn-1")
    judged = turn.get_span_context()
    (verdict,) = result.verdicts
    assert verdict.value == Helpfulness(rating=2, resolved=True, reason="fine")
    assert verdict.trace_id == trace.format_trace_id(judged.trace_id)
    assert {s.name for s in sink.scores.values()} == {
        "helpful.rating",
        "helpful.resolved",
        "helpful.category",
        "helpful.reason",
    }
    assert {(s.trace_id, s.span_id) for s in sink.scores.values()} == {
        (trace.format_trace_id(judged.trace_id), trace.format_span_id(judged.span_id))
    }
    evaluate = next(s for s in spans.finished() if s.name.startswith("evalr.evaluate"))
    assert evaluate.parent is not None
    assert evaluate.parent.span_id == judged.span_id


async def test_a_judged_span_can_be_given_after_it_ended(spans: Spans) -> None:
    tracer = spans.provider.get_tracer("app")
    with tracer.start_as_current_span("turn") as turn:
        judged = turn.get_span_context()
    result = await OnlineEvaluation([evaluator(spans)]).judge(THREAD, key="k", span=judged)
    (verdict,) = result.verdicts
    assert verdict.trace_id == trace.format_trace_id(judged.trace_id)


async def test_outside_any_trace_scores_have_no_trace() -> None:
    sink = InMemoryScoreSink()
    await OnlineEvaluation([evaluator()], sinks=[sink]).judge(THREAD, key="k")
    assert {(s.trace_id, s.span_id) for s in sink.scores.values()} == {(None, None)}


async def test_failures_are_recorded_not_raised() -> None:
    online = OnlineEvaluation(
        [
            FunctionEvaluator(declining, verdict_type=Helpfulness),
            FunctionEvaluator(failing, verdict_type=Helpfulness),
            evaluator(),
        ],
        sinks=[BrokenSink()],
    )
    result = await online.judge(THREAD, key="k")
    assert result.handed_off == ("declining",)
    assert result.errors == (
        "failing: RuntimeError: down",
        "BrokenSink: ConnectionError: unreachable",
    )
    assert len(result.verdicts) == 1


async def test_the_budget_limits_evaluations() -> None:
    budget = Budget(max_evaluations=3)
    online = OnlineEvaluation(
        [FunctionEvaluator(declining, verdict_type=Helpfulness), evaluator()], budget=budget
    )
    first = await online.judge(THREAD, key="a")
    second = await online.judge(THREAD, key="b")
    assert (len(first.verdicts), first.skipped) == (1, ())
    assert (second.handed_off, second.skipped) == (("declining",), ("judge",))
    assert budget.evaluations == 3


async def test_submitted_inputs_are_judged_in_the_background(spans: Spans) -> None:
    online = OnlineEvaluation([evaluator(spans)], max_concurrency=2)
    tracer = spans.provider.get_tracer("app")
    with tracer.start_as_current_span("turn") as turn:
        tasks = [online.submit(THREAD, key=f"turn-{i}") for i in range(5)]
    results = await online.drain()
    assert len(results) == 5
    assert all(t.done() for t in tasks)
    assert {v.trace_id for r in results for v in r.verdicts} == {
        trace.format_trace_id(turn.get_span_context().trace_id)
    }
    assert await online.drain() == []


def test_the_sample_rate_is_a_share() -> None:
    with pytest.raises(ValueError, match="sample_rate"):
        OnlineEvaluation([evaluator()], sample_rate=1.5)
