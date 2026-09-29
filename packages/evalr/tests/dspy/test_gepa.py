from typing import Literal

import dspy
import pytest
from pydantic import BaseModel

from evalr.contracts import check_optimizer
from evalr.core import DatasetRef, Example, Optimizer, measure, optimize
from evalr.dspy import DspyJudge, Gepa, feedback_metric

from .scripted import MARKER, InstructionAware, Reply, Score, pluses, reflection_lm

TRAIN = pluses("train", [2, 3, 4, 5])
VALIDATE = pluses("validate", [1, 2, 3, 5])


def gepa() -> Gepa:
    return Gepa(
        reflection_lm=reflection_lm(),
        max_metric_calls=12,
        reflection_minibatch_size=2,
        use_merge=False,
    )


async def test_a_trained_judge_beats_its_untrained_self() -> None:
    judge = DspyJudge(Score, inputs=Reply, lm=InstructionAware())
    before = await measure(judge, VALIDATE)
    trained = await optimize(judge, train=TRAIN, validate=VALIDATE, optimizer=gepa())
    after = await measure(trained, VALIDATE)

    assert before.agreement.score is not None
    assert after.agreement.score is not None
    assert after.agreement.score > before.agreement.score
    assert after.agreement.score == 1.0
    assert trained.instructions == MARKER
    assert judge.instructions != MARKER
    assert trained.version != judge.version
    assert trained.training is not None
    assert judge.training is None
    assert trained.training.optimizer == "gepa"
    assert trained.training.base_version == judge.version
    assert trained.training.train == DatasetRef.of(TRAIN)
    assert trained.training.validation == DatasetRef(
        name="validate", version=VALIDATE.version, size=4
    )
    assert trained.training.score_after == 1.0
    assert trained.training.score_before == pytest.approx(before.agreement.score)
    assert trained.training.settings["max_metric_calls"] == 12
    assert trained.training.settings["reflection_lm"] == "dummy"


async def test_gepa_meets_the_optimizer_contract() -> None:
    optimizer: Optimizer[Reply, Score, DspyJudge[Reply, Score]] = gepa()
    await check_optimizer(
        optimizer,
        DspyJudge(Score, inputs=Reply, lm=InstructionAware()),
        train=TRAIN,
        validate=VALIDATE,
    )


def test_one_budget_at_most() -> None:
    assert Gepa(reflection_lm=reflection_lm()).auto == "light"
    assert Gepa(reflection_lm=reflection_lm(), max_full_evals=2).auto is None
    with pytest.raises(ValueError, match="give one of"):
        Gepa(reflection_lm=reflection_lm(), auto="heavy", max_metric_calls=10)


def test_training_examples_need_a_verdict() -> None:
    judge = DspyJudge(Score, inputs=Reply)
    unlabelled = Example[Reply, Score](id="x", input=Reply(request="r", reply="+"))
    with pytest.raises(ValueError, match="x has no verdict"):
        judge.training_example(unlabelled)
    labelled = judge.training_example(next(iter(TRAIN)))
    assert labelled.inputs().toDict() == {"request": "Rate this reply", "reply": "++"}
    assert labelled.labels().toDict() == {
        "rating": 2,
        "resolved": False,
        "reason": "it has 2 pluses",
    }


def metric_on(pred: dspy.Prediction, reason: str | None = "slow refund") -> dspy.Prediction:
    judge = DspyJudge(Score, inputs=Reply)
    gold = dspy.Example(request="r", reply="+", rating=4, resolved=True, reason=reason)
    result = feedback_metric(judge)(gold.with_inputs("request", "reply"), pred, None, None, None)
    assert isinstance(result, dspy.Prediction)
    return result


def test_feedback_names_each_wrong_field_and_quotes_peoples_reasons() -> None:
    result = metric_on(dspy.Prediction(rating=2, resolved=True, reason="None"))
    assert result.get("score") == pytest.approx((0.5 + 1.0) / 2)
    assert result.get("feedback") == (
        "rating: you said 2, people said 4.\nPeople's reason: slow refund"
    )


def test_feedback_when_the_judge_agrees() -> None:
    result = metric_on(dspy.Prediction(rating=4, resolved=True, reason=None), reason=None)
    assert (result.get("score"), result.get("feedback")) == (
        1.0,
        "You agreed with people on every field.",
    )


def test_an_invalid_answer_scores_zero_and_says_why() -> None:
    result = metric_on(dspy.Prediction(rating=9, resolved=True, reason=None))
    assert result.get("score") == 0.0
    feedback = result.get("feedback")
    assert isinstance(feedback, str)
    assert feedback.startswith("The answer was not a valid Score: rating: Input should be less")
    assert feedback.endswith("People's reason: slow refund")


def test_nothing_compared_is_full_agreement() -> None:
    class Remark(BaseModel):
        tone: Literal["warm", "cold"] | None = None
        note: str | None = None

    judge = DspyJudge(Remark, inputs=Reply)
    gold = dspy.Example(request="r", reply="+", tone=None, note="terse").with_inputs(
        "request", "reply"
    )
    result = feedback_metric(judge)(
        gold, dspy.Prediction(tone="cold", note="null"), None, None, None
    )
    assert (result.get("score"), result.get("feedback")) == (
        1.0,
        "You agreed with people on every field.\nPeople's note: terse",
    )
