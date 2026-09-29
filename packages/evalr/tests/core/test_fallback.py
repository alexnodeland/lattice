from typing import cast

import pytest
from pydantic import BaseModel

from evalr import Evaluator, Fallback, FunctionEvaluator

from ..conftest import Spans
from .models import Helpfulness, Scripted, Thread

GOOD = Helpfulness(rating=5, resolved=True)
BAD = Helpfulness(rating=1, resolved=False)


def thread(first: str) -> Thread:
    return Thread(messages=[first])


def primary() -> Scripted:
    return Scripted(
        {
            "sure": (GOOD, {"rating": 0.9, "resolved": 0.95}),
            "unsure": (GOOD, {"rating": 0.9, "resolved": 0.4}),
            "blank": (GOOD, {}),
        },
        name="jev",
        hand_off=frozenset({"declined"}),
    )


def backup() -> Scripted:
    answers = {k: (BAD, {}) for k in ("sure", "unsure", "blank", "declined")}
    return Scripted(answers, name="judge", version="7")


def attributes(spans: Spans) -> dict[str, object]:
    (span,) = [s for s in spans.finished() if s.name.startswith("evalr.fallback")]
    return dict(span.attributes or {})


async def test_a_confident_primary_is_kept(spans: Spans) -> None:
    both = Fallback(primary(), backup(), min_confidence=0.5, tracer_provider=spans.provider)
    verdict = await both.evaluate(thread("sure"))
    assert (verdict.value, verdict.evaluator) == (GOOD, "jev")
    assert attributes(spans)["evalr.fallback.handed_off"] is False


async def test_a_hand_off_goes_to_the_fallback(spans: Spans) -> None:
    both = Fallback(primary(), backup(), tracer_provider=spans.provider)
    verdict = await both.evaluate(thread("declined"))
    assert (verdict.value, verdict.evaluator, verdict.version) == (BAD, "judge", "7")
    recorded = attributes(spans)
    assert recorded["evalr.fallback.handed_off"] is True
    assert recorded["evalr.fallback.reason"] == "jev handed off: unsure about declined"
    assert recorded["evalr.evaluator.name"] == "jev+judge"


async def test_low_confidence_goes_to_the_fallback(spans: Spans) -> None:
    both = Fallback(primary(), backup(), min_confidence=0.5, tracer_provider=spans.provider)
    assert (await both.evaluate(thread("unsure"))).evaluator == "judge"
    assert attributes(spans)["evalr.fallback.reason"] == "jev was unsure of resolved"


async def test_without_a_threshold_or_confidence_the_primary_is_kept() -> None:
    assert (await Fallback(primary(), backup()).evaluate(thread("unsure"))).evaluator == "jev"
    thresholded = Fallback(primary(), backup(), min_confidence=0.99)
    assert (await thresholded.evaluate(thread("blank"))).evaluator == "jev"


async def test_other_failures_propagate() -> None:
    def broken(t: Thread) -> Helpfulness:
        raise RuntimeError("down")

    both = Fallback(FunctionEvaluator(broken, verdict_type=Helpfulness), backup())
    with pytest.raises(RuntimeError, match="down"):
        await both.evaluate(thread("sure"))


def test_identity() -> None:
    both = Fallback(primary(), backup(), min_confidence=0.5, name="cheap-then-careful")
    assert (both.name, both.verdict_type) == ("cheap-then-careful", Helpfulness)
    assert len(both.version) == 12
    assert both.version == Fallback(primary(), backup(), min_confidence=0.5).version
    assert both.version != Fallback(primary(), backup(), min_confidence=0.6).version


def test_the_verdict_types_must_match() -> None:
    class Other(BaseModel):
        ok: bool

    other = FunctionEvaluator(lambda t: Other(ok=True), verdict_type=Other, name="other")
    with pytest.raises(TypeError, match="jev gives Helpfulness but other gives Other"):
        Fallback(primary(), cast(Evaluator[Thread, Helpfulness], other))


@pytest.mark.parametrize("threshold", [-0.1, 1.1])
def test_the_threshold_is_a_probability(threshold: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        Fallback(primary(), backup(), min_confidence=threshold)
