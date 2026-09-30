"""Two adapters of the Evaluator port, composed by the core: a decision model, then a DSPy judge."""

from dspy.utils import DummyLM

from evalr import Fallback
from evalr.contracts import check_evaluator
from evalr.decision import DecisionEvaluator
from evalr.dspy import DspyJudge

from .conftest import Spans
from .decision.jev import FakeJev
from .decision.models import Helpfulness, Thread, Tone, thread

SURE = {
    "rating": {"choice": "4", "confidence": 0.9},
    "resolved": {"noul": 0.9},
    "category": {"choice": "billing", "confidence": 0.9},
    "tone": {"choice": "warm", "confidence": 0.9},
}
JUDGED = {
    "rating": "2",
    "resolved": "False",
    "category": "bug",
    "tone": "cold",
    "share": "0.3",
    "reason": "The reply did not say when the refund arrives",
}


def evaluator(spans: Spans) -> Fallback[Thread, Helpfulness]:
    jev = FakeJev({"": SURE, "ambiguous": {"rating": {"choice": "3", "confidence": 0.3}}})
    decider = DecisionEvaluator(
        Helpfulness,
        inputs=Thread,
        model=jev.model(),
        min_confidence=0.6,
        tracer_provider=spans.provider,
    )
    judge = DspyJudge(
        Helpfulness, inputs=Thread, lm=DummyLM([JUDGED] * 10), tracer_provider=spans.provider
    )
    return Fallback(decider, judge, tracer_provider=spans.provider)


async def test_the_decision_model_judges_what_it_is_sure_of(spans: Spans) -> None:
    verdict = await evaluator(spans).evaluate(thread("clear"))
    assert verdict.evaluator == "helpfulness-decision"
    assert verdict.value.rating == 4
    assert verdict.value.reason is None
    assert verdict.confidence["rating"] == 0.9
    assert verdict.cost is not None


async def test_unsure_inputs_go_to_the_judge_which_fills_the_text(spans: Spans) -> None:
    verdict = await evaluator(spans).evaluate(thread("ambiguous"))
    assert verdict.evaluator == "helpfulness-judge"
    assert verdict.value == Helpfulness(
        rating=2,
        resolved=False,
        category="bug",
        tone=Tone.COLD,
        share=0.3,
        reason="The reply did not say when the refund arrives",
    )
    assert verdict.confidence == {}
    names = [s.name for s in spans.finished()]
    assert names == [
        "evalr.evaluate helpfulness-decision",
        "evalr.evaluate helpfulness-judge",
        "evalr.fallback helpfulness-decision+helpfulness-judge",
    ]
    fallback = spans.finished()[-1]
    assert dict(fallback.attributes or {})["evalr.fallback.reason"] == (
        "helpfulness-decision handed off: confidence in rating is 0.30, below 0.6"
    )


async def test_the_composition_meets_the_evaluator_contract(spans: Spans) -> None:
    await check_evaluator(evaluator(spans), [thread("clear"), thread("ambiguous")])
