from typing import Any, Literal

import pytest
from pydantic import BaseModel
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.decision import UnsureRoute
from pydantic_ai.models.function import AgentInfo, FunctionModel

from evalr.contracts import check_optimizer
from evalr.core import Dataset, DatasetRef, Example, Optimizer, optimize
from evalr.decision import DecisionEvaluator, ThresholdCalibration

from .jev import FakeJev
from .models import Helpfulness, Thread, Tone, thread

SURE_REST = {
    "category": {"choice": "billing", "confidence": 0.95},
    "tone": {"choice": "warm", "confidence": 0.95},
}


def case(
    i: int, *, p: float, resolved: bool, rating: int, said: int, confidence: float
) -> tuple[Example[Thread, Helpfulness], dict[str, dict[str, dict[str, Any]]]]:
    """An example people labelled, and what the fake Jev answers for it."""
    key = f"case-{i:02d}"
    example = Example[Thread, Helpfulness](
        id=key,
        input=thread(key),
        verdict=Helpfulness(rating=rating, resolved=resolved, category="billing", tone=Tone.WARM),
    )
    answers = {
        "resolved": {"noul": p},
        "rating": {"choice": str(said), "confidence": confidence},
        **SURE_REST,
    }
    return example, {key: answers}


def build(
    name: str,
    cases: list[tuple[Example[Thread, Helpfulness], dict[str, dict[str, dict[str, Any]]]]],
) -> tuple[Dataset[Thread, Helpfulness], dict[str, dict[str, dict[str, Any]]]]:
    script: dict[str, dict[str, dict[str, Any]]] = {}
    for _, answers in cases:
        script.update(answers)
    return Dataset(name, [e for e, _ in cases], input_type=Thread, verdict_type=Helpfulness), script


# Jev says yes too readily: people say resolved only when its probability is 0.7 or more.
OVERCONFIDENT_TRAIN = [
    case(0, p=0.55, resolved=False, rating=4, said=4, confidence=0.9),
    case(1, p=0.62, resolved=False, rating=3, said=3, confidence=0.9),
    case(2, p=0.66, resolved=False, rating=5, said=5, confidence=0.9),
    case(3, p=0.75, resolved=True, rating=2, said=2, confidence=0.9),
    case(4, p=0.85, resolved=True, rating=4, said=4, confidence=0.9),
]
OVERCONFIDENT_VALIDATE = [
    case(10, p=0.6, resolved=False, rating=4, said=4, confidence=0.9),
    case(11, p=0.9, resolved=True, rating=3, said=3, confidence=0.9),
]


def decider(script: dict[str, dict[str, dict[str, Any]]]) -> DecisionEvaluator[Thread, Helpfulness]:
    return DecisionEvaluator(Helpfulness, inputs=Thread, model=FakeJev(script).model())


async def test_the_boolean_threshold_is_fitted_to_people() -> None:
    train, script = build("train", OVERCONFIDENT_TRAIN)
    validate, more = build("validate", OVERCONFIDENT_VALIDATE)
    evaluator = decider({**script, **more})
    calibrated = await optimize(
        evaluator,
        train=train,
        validate=validate,
        optimizer=ThresholdCalibration(target_agreement=0.0),
    )
    assert calibrated.boolean_threshold == 0.7
    assert calibrated.min_confidence is None
    assert calibrated.version != evaluator.version
    training = calibrated.training
    assert training is not None
    assert (training.optimizer, training.base_version) == ("thresholds", evaluator.version)
    assert training.train == DatasetRef.of(train)
    assert training.score_before == pytest.approx((0.8 + 1.0) / 2)
    assert training.score_after == 1.0
    assert training.results == {
        "boolean_threshold": 0.7,
        "min_confidence": None,
        "coverage_before": 1.0,
        "coverage_after": 1.0,
    }
    assert training.settings["target_agreement"] == 0.0
    verdict = await calibrated.evaluate(thread("case-10"))
    assert verdict.value.resolved is False


# Jev is right when sure and wrong when unsure about the rating.
UNSURE_TRAIN = [
    case(0, p=0.95, resolved=True, rating=4, said=4, confidence=0.9),
    case(1, p=0.05, resolved=False, rating=2, said=2, confidence=0.8),
    case(2, p=0.95, resolved=True, rating=1, said=5, confidence=0.3),
    case(3, p=0.05, resolved=False, rating=5, said=1, confidence=0.25),
]
UNSURE_VALIDATE = [
    case(10, p=0.95, resolved=True, rating=3, said=3, confidence=0.85),
    case(11, p=0.95, resolved=True, rating=2, said=4, confidence=0.2),
]


async def test_the_hand_off_threshold_reaches_the_target_on_what_is_kept() -> None:
    train, script = build("train", UNSURE_TRAIN)
    validate, more = build("validate", UNSURE_VALIDATE)
    calibrated = await optimize(
        decider({**script, **more}),
        train=train,
        validate=validate,
        optimizer=ThresholdCalibration(target_agreement=1.0),
    )
    assert calibrated.min_confidence == 0.35
    training = calibrated.training
    assert training is not None
    assert training.score_after == 1.0
    assert training.results["coverage_after"] == 0.5
    assert training.results["coverage_before"] == 1.0
    assert training.score_before is not None
    assert training.score_before < 1.0


async def test_an_unreachable_target_settles_for_the_best_agreement() -> None:
    confident_and_wrong = [
        case(0, p=0.95, resolved=True, rating=4, said=4, confidence=0.9),
        case(1, p=0.95, resolved=True, rating=1, said=5, confidence=0.95),
    ]
    train, script = build("train", confident_and_wrong)
    validate, more = build("validate", UNSURE_VALIDATE)
    calibrated = await optimize(
        decider({**script, **more}),
        train=train,
        validate=validate,
        optimizer=ThresholdCalibration(target_agreement=1.0),
    )
    assert calibrated.min_confidence is None


class Plain(BaseModel):
    grade: Literal["a", "b"]


def graded(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    text = str(getattr(messages[-1].parts[-1], "content", ""))
    if "skip" in text:
        raise UnsureRoute("scripted", "PlainDecision", {"PlainDecision": 0.2}, 0.5)
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"grade": "a"})])


class Case(BaseModel):
    text: str


def plain(name: str, texts: list[str]) -> Dataset[Case, Plain]:
    examples = [
        Example[Case, Plain](id=f"{name}-{i}", input=Case(text=t), verdict=Plain(grade="a"))
        for i, t in enumerate(texts)
    ]
    return Dataset(name, examples, input_type=Case, verdict_type=Plain)


async def test_without_yes_or_no_fields_the_boolean_threshold_stays_and_hand_offs_are_skipped() -> (
    None
):
    evaluator = DecisionEvaluator(
        Plain, inputs=Case, model=FunctionModel(graded), boolean_threshold=0.6
    )
    calibrated = await optimize(
        evaluator,
        train=plain("train", ["one", "skip this", "two"]),
        validate=plain("validate", ["three", "skip that"]),
        optimizer=ThresholdCalibration(),
    )
    assert calibrated.boolean_threshold == 0.6
    training = calibrated.training
    assert training is not None
    assert (training.score_before, training.score_after) == (1.0, 1.0)


async def test_threshold_calibration_meets_the_optimizer_contract() -> None:
    train, script = build("train", OVERCONFIDENT_TRAIN)
    validate, more = build("validate", OVERCONFIDENT_VALIDATE)
    optimizer: Optimizer[Thread, Helpfulness, DecisionEvaluator[Thread, Helpfulness]] = (
        ThresholdCalibration(target_agreement=0.5)
    )
    await check_optimizer(optimizer, decider({**script, **more}), train=train, validate=validate)


@pytest.mark.parametrize(
    ("target", "grid", "message"),
    [(1.5, (0.5,), "target_agreement"), (0.9, (0.0, 0.5), "grid"), (0.9, (), "grid")],
)
def test_settings_are_checked(target: float, grid: tuple[float, ...], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ThresholdCalibration(target_agreement=target, grid=grid)


def test_the_default_grid() -> None:
    calibration = ThresholdCalibration()
    assert calibration.grid[0] == 0.05
    assert calibration.grid[-1] == 0.95
    assert len(calibration.grid) == 19


class Opinion(BaseModel):
    tone: Literal["warm", "cold"] | None = None


def opinionated(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"tone": "warm"})])


async def test_verdicts_with_nothing_compared_leave_the_scores_unknown() -> None:
    def data(name: str) -> Dataset[Case, Opinion]:
        example = Example[Case, Opinion](id=f"{name}-0", input=Case(text="x"), verdict=Opinion())
        return Dataset(name, [example], input_type=Case, verdict_type=Opinion)

    calibrated = await optimize(
        DecisionEvaluator(Opinion, inputs=Case, model=FunctionModel(opinionated)),
        train=data("train"),
        validate=data("validate"),
        optimizer=ThresholdCalibration(),
    )
    training = calibrated.training
    assert training is not None
    assert (training.score_before, training.score_after, calibrated.min_confidence) == (
        None,
        None,
        None,
    )
