from typing import cast

import pytest
from opentelemetry import trace
from pydantic import BaseModel

from evalr import Evaluator, FunctionEvaluator, UnsupportedField, Verdict
from evalr.core import current_trace_id, get_tracer

from ..conftest import Spans, context_of
from .models import Helpfulness, Thread


def judge(thread: Thread) -> Helpfulness:
    return Helpfulness(rating=len(thread.messages), resolved=True)


async def ajudge(thread: Thread) -> Helpfulness:
    return Helpfulness(rating=1, resolved=False)


THREAD = Thread(messages=["hi", "hello", "thanks"])


async def test_a_sync_function_is_an_evaluator(spans: Spans) -> None:
    evaluator = FunctionEvaluator(
        judge, verdict_type=Helpfulness, version="2", tracer_provider=spans.provider
    )
    verdict = await evaluator.evaluate(THREAD)
    assert verdict.value == Helpfulness(rating=3, resolved=True)
    assert (verdict.evaluator, verdict.version, verdict.cost, verdict.confidence) == (
        "judge",
        "2",
        None,
        {},
    )
    assert verdict.latency >= 0.0
    (span,) = spans.finished()
    assert span.name == "evalr.evaluate judge"
    assert span.instrumentation_scope is not None
    assert span.instrumentation_scope.name == "evalr"
    assert dict(span.attributes or {}) == {
        "evalr.evaluator.name": "judge",
        "evalr.evaluator.version": "2",
        "evalr.verdict.type": "Helpfulness",
    }
    assert verdict.trace_id == trace.format_trace_id(context_of(span).trace_id)


async def test_an_async_function_is_an_evaluator(spans: Spans) -> None:
    evaluator = FunctionEvaluator(
        ajudge, verdict_type=Helpfulness, name="quick", tracer_provider=spans.provider
    )
    verdict = await evaluator.evaluate(THREAD)
    assert (verdict.value.rating, verdict.evaluator, verdict.version) == (1, "quick", "1")
    assert evaluator.name == "quick"
    assert evaluator.version == "1"
    assert evaluator.verdict_type is Helpfulness


async def test_verdicts_record_the_enclosing_trace(spans: Spans) -> None:
    evaluator = FunctionEvaluator(judge, verdict_type=Helpfulness, tracer_provider=spans.provider)
    with get_tracer(spans.provider).start_as_current_span("experiment item") as parent:
        verdict = await evaluator.evaluate(THREAD)
        assert current_trace_id() == trace.format_trace_id(parent.get_span_context().trace_id)
    assert verdict.trace_id == trace.format_trace_id(parent.get_span_context().trace_id)
    child, root = spans.finished()
    assert child.parent is not None
    assert child.parent.span_id == context_of(root).span_id


async def test_without_a_trace_there_is_no_trace_id() -> None:
    evaluator = FunctionEvaluator(
        judge, verdict_type=Helpfulness, tracer_provider=trace.NoOpTracerProvider()
    )
    verdict = await evaluator.evaluate(THREAD)
    assert verdict.trace_id is None
    assert current_trace_id() is None


async def test_a_wrong_return_type_fails_and_is_recorded(spans: Spans) -> None:
    class Other(BaseModel):
        ok: bool

    def wrong(thread: Thread) -> Helpfulness:
        return cast(Helpfulness, Other(ok=True))

    evaluator = FunctionEvaluator(wrong, verdict_type=Helpfulness, tracer_provider=spans.provider)
    with pytest.raises(TypeError, match="wrong returned Other, not Helpfulness"):
        await evaluator.evaluate(THREAD)
    (span,) = spans.finished()
    assert not span.status.is_ok
    assert [e.name for e in span.events] == ["exception"]


def test_unjudgeable_verdict_types_are_rejected_up_front() -> None:
    class Listy(BaseModel):
        tags: list[str]

    with pytest.raises(UnsupportedField):
        FunctionEvaluator(lambda thread: Listy(tags=[]), verdict_type=Listy)


async def test_evaluators_of_different_verdict_types_share_the_protocol() -> None:
    class Brevity(BaseModel):
        short: bool

    def brief(thread: Thread) -> Brevity:
        return Brevity(short=len(thread.messages) < 5)

    evaluators: list[Evaluator[Thread, BaseModel]] = [
        FunctionEvaluator(judge, verdict_type=Helpfulness),
        FunctionEvaluator(brief, verdict_type=Brevity),
    ]
    verdicts: list[Verdict[BaseModel]] = [await e.evaluate(THREAD) for e in evaluators]
    assert [type(v.value) for v in verdicts] == [Helpfulness, Brevity]
