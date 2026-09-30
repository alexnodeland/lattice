import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.decision import UnsureRoute
from pydantic_ai.models.function import AgentInfo, FunctionModel

from evalr.contracts import check_evaluator
from evalr.core import HandOff, Training
from evalr.decision import DEFAULT_MODEL, DecisionEvaluator
from evalr.decision.evaluators import _probability_of_yes

from ..conftest import Spans, context_of
from .jev import FakeJev
from .models import Helpfulness, Thread, Tone, thread

SURE = {
    "rating": {"choice": "4", "confidence": 0.9},
    "resolved": {"noul": 0.7},
    "category": {"choice": "billing", "confidence": 0.8},
    "tone": {"choice": "warm", "confidence": 0.85},
    "share": {"noul": 0.25},
}


def decider(
    jev: FakeJev, *, boolean_threshold: float | None = None, min_confidence: float | None = None
) -> DecisionEvaluator[Thread, Helpfulness]:
    return DecisionEvaluator(
        Helpfulness,
        inputs=Thread,
        model=jev.model(),
        boolean_threshold=boolean_threshold,
        min_confidence=min_confidence,
    )


async def test_a_decision_model_gives_a_typed_verdict_with_confidence(spans: Spans) -> None:
    jev = FakeJev({"": SURE})
    evaluator = DecisionEvaluator(
        Helpfulness, inputs=Thread, model=jev.model(), tracer_provider=spans.provider
    )
    verdict = await evaluator.evaluate(thread("charged twice"))
    assert verdict.value == Helpfulness(
        rating=4, resolved=True, category="billing", tone=Tone.WARM, share=0.25, reason=None
    )
    assert verdict.confidence == pytest.approx(
        {"rating": 0.9, "resolved": 0.7, "category": 0.8, "tone": 0.85}
    )
    assert verdict.cost == pytest.approx(0.000042)
    assert (verdict.evaluator, verdict.version) == ("helpfulness-decision", evaluator.version)
    (span,) = [s for s in spans.finished() if s.name.startswith("evalr.evaluate")]
    assert dict(span.attributes or {})["gen_ai.response.model"] == "jev-1.13.0"
    assert verdict.trace_id == f"{context_of(span).trace_id:032x}"
    (request,) = jev.requests
    assert "charged twice" in request["state"]
    assert set(request["questions"]) == {"rating", "resolved", "category", "tone", "share"}


async def test_a_no_is_as_confident_as_its_probability() -> None:
    evaluator = decider(FakeJev({"": {**SURE, "resolved": {"noul": 0.2}}}))
    verdict = await evaluator.evaluate(thread("x"))
    assert verdict.value.resolved is False
    assert verdict.confidence["resolved"] == pytest.approx(0.8)


async def test_the_boolean_threshold_decides_yes() -> None:
    jev = FakeJev({"": SURE})
    decision = await decider(jev, boolean_threshold=0.75).decide(thread("x"))
    assert decision.value.resolved is False
    assert decision.probabilities == {"resolved": pytest.approx(0.7)}
    assert decision.confidence["resolved"] == pytest.approx(0.3)
    assert decision.model == "jev-1.13.0"


@pytest.mark.parametrize(
    ("threshold", "answer", "reported"),
    # pydantic-ai's own numbers for a probability of yes of 0.7, from a run against it.
    [(0.5, True, 0.4), (0.6, True, 0.25), (0.75, False, 0.066667), (0.9, False, 0.222222)],
)
async def test_the_probability_of_yes_is_recovered_from_pydantic_ais_confidence(
    threshold: float, answer: bool, reported: float
) -> None:
    assert _probability_of_yes(answer, reported, threshold) == pytest.approx(0.7, abs=1e-5)
    decision = await decider(FakeJev({"": SURE}), boolean_threshold=threshold).decide(thread("x"))
    assert decision.value.resolved is answer
    assert decision.probabilities["resolved"] == pytest.approx(0.7, abs=1e-5)


async def test_an_unsure_decision_is_handed_off(spans: Spans) -> None:
    jev = FakeJev({"": SURE, "ambiguous": {"rating": {"choice": "3", "confidence": 0.4}}})
    evaluator = DecisionEvaluator(
        Helpfulness,
        inputs=Thread,
        model=jev.model(),
        min_confidence=0.6,
        tracer_provider=spans.provider,
    )
    assert (await evaluator.evaluate(thread("clear"))).value.rating == 4
    with pytest.raises(HandOff, match=r"confidence in rating is 0\.40, below 0\.6"):
        await evaluator.evaluate(thread("ambiguous"))
    handed = spans.finished()[-1]
    assert dict(handed.attributes or {})["evalr.handed_off"] is True
    assert handed.status.is_ok
    assert not handed.events


async def test_pydantic_ais_hand_off_is_a_hand_off() -> None:
    def unsure(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise UnsureRoute("jev", "HelpfulnessDecision", {"HelpfulnessDecision": 0.4}, 0.5)

    evaluator = DecisionEvaluator(Helpfulness, inputs=Thread, model=FunctionModel(unsure))
    with pytest.raises(HandOff, match="the decision model handed off") as raised:
        await evaluator.evaluate(thread("x"))
    assert isinstance(raised.value.__cause__, UnsureRoute)


async def test_service_failures_are_not_hand_offs() -> None:
    with pytest.raises(ModelHTTPError):
        await decider(FakeJev({}, status=500)).evaluate(thread("x"))


def test_it_is_built_without_credentials() -> None:
    evaluator = DecisionEvaluator(Helpfulness, inputs=Thread)
    assert evaluator.model_name == DEFAULT_MODEL
    assert evaluator.name == "helpfulness-decision"
    assert (evaluator.verdict_type, evaluator.input_type) == (Helpfulness, Thread)
    assert evaluator.view.left_out == ("reason",)
    assert (evaluator.boolean_threshold, evaluator.min_confidence, evaluator.training) == (
        0.5,
        None,
        None,
    )


def test_the_version_follows_the_model_types_instructions_and_thresholds() -> None:
    base = DecisionEvaluator(Helpfulness, inputs=Thread).version
    jev = FakeJev({})
    assert DecisionEvaluator(Helpfulness, inputs=Thread, model=jev.model()).version == base
    assert DecisionEvaluator(Helpfulness, inputs=Thread, boolean_threshold=0.5).version == base
    assert DecisionEvaluator(Helpfulness, inputs=Thread, name="other").version == base
    for changed in (
        DecisionEvaluator(Helpfulness, inputs=Thread, model="typesafe:jev-1.13.0"),
        DecisionEvaluator(Helpfulness, inputs=Thread, boolean_threshold=0.6),
        DecisionEvaluator(Helpfulness, inputs=Thread, min_confidence=0.6),
        DecisionEvaluator(Helpfulness, inputs=Thread, instructions="Be strict."),
    ):
        assert changed.version != base


def test_calibrated_copies_carry_their_thresholds_and_training() -> None:
    evaluator = DecisionEvaluator(Helpfulness, inputs=Thread)
    training = Training.model_validate(
        {
            "optimizer": "thresholds",
            "settings": {},
            "base_version": evaluator.version,
            "train": {"name": "t", "version": "v", "size": 1},
            "validation": {"name": "v", "version": "v", "size": 1},
            "score_before": 0.5,
            "score_after": 0.9,
        }
    )
    tuned = evaluator.calibrated(boolean_threshold=0.65, min_confidence=0.7, training=training)
    assert (tuned.boolean_threshold, tuned.min_confidence, tuned.training) == (0.65, 0.7, training)
    assert tuned.version != evaluator.version
    assert evaluator.training is None
    with pytest.raises(ValueError, match="boolean_threshold"):
        evaluator.calibrated(boolean_threshold=1.0, min_confidence=None, training=training)


def test_thresholds_are_checked() -> None:
    with pytest.raises(ValueError, match="boolean_threshold"):
        DecisionEvaluator(Helpfulness, inputs=Thread, boolean_threshold=0.0)
    with pytest.raises(ValueError, match="min_confidence"):
        DecisionEvaluator(Helpfulness, inputs=Thread, min_confidence=1.5)


async def test_the_decision_evaluator_meets_the_evaluator_contract() -> None:
    evaluator = decider(FakeJev({"": SURE}), min_confidence=0.6)
    await check_evaluator(evaluator, [thread("a"), thread("b")])
