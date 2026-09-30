"""Every evaluator and optimizer meets its port's contract."""

from typing import cast

import pytest
from pydantic import BaseModel

from evalr import Fallback, FunctionEvaluator, Verdict
from evalr.contracts import ContractViolation, check_evaluator, check_optimizer
from evalr.core import Dataset, Evaluator, Example
from evalr.memory import BestOf

from ..conftest import Spans
from ..core.models import Helpfulness, Scripted, Thread

INPUTS = [Thread(messages=[str(i)]) for i in range(4)]


def judge(thread: Thread) -> Helpfulness:
    return Helpfulness(rating=1 + int(thread.messages[0]), resolved=True)


def scripted(**kw: frozenset[str]) -> Scripted:
    return Scripted(
        {
            str(i): (Helpfulness(rating=3, resolved=False), {"rating": 0.3 * (i % 3)})
            for i in range(4)
        },
        name="jev",
        hand_off=kw.get("hand_off", frozenset()),
    )


async def test_function_evaluators_meet_the_contract(spans: Spans) -> None:
    await check_evaluator(FunctionEvaluator(judge, verdict_type=Helpfulness), INPUTS)
    await check_evaluator(
        FunctionEvaluator(judge, verdict_type=Helpfulness, tracer_provider=spans.provider), INPUTS
    )


async def test_fallbacks_meet_the_contract() -> None:
    both = Fallback(
        scripted(hand_off=frozenset({"1"})),
        FunctionEvaluator(judge, verdict_type=Helpfulness),
        min_confidence=0.5,
    )
    await check_evaluator(both, INPUTS)


async def test_an_evaluator_may_hand_off_some_inputs() -> None:
    await check_evaluator(scripted(hand_off=frozenset({"0", "2"})), INPUTS)


class Untraced(Scripted):
    async def evaluate(self, input: Thread, /) -> Verdict[Helpfulness]:
        verdict = await super().evaluate(input)
        return verdict.model_copy(update={"trace_id": None})


class Anonymous(Scripted):
    async def evaluate(self, input: Thread, /) -> Verdict[Helpfulness]:
        verdict = await super().evaluate(input)
        return verdict.model_copy(update={"evaluator": ""})


class Restless(Scripted):
    async def evaluate(self, input: Thread, /) -> Verdict[Helpfulness]:
        self.version = str(self.calls)
        return await super().evaluate(input)


class Mistyped(Scripted):
    async def evaluate(self, input: Thread, /) -> Verdict[Helpfulness]:
        class Other(BaseModel):
            x: int = 1

        verdict = await super().evaluate(input)
        return cast(Verdict[Helpfulness], verdict.model_copy(update={"value": Other()}))


ANSWERS = {str(i): (Helpfulness(rating=3, resolved=False), {}) for i in range(4)}


@pytest.mark.parametrize(
    ("broken", "message"),
    [
        (Untraced(ANSWERS), "record the trace"),
        (Anonymous(ANSWERS), "name the evaluator"),
        (Restless(ANSWERS), "must not change the evaluator's name or version"),
        (Mistyped(ANSWERS), "must be a Helpfulness"),
        (Scripted(ANSWERS, hand_off=frozenset(ANSWERS)), "judge at least one"),
    ],
    ids=["untraced", "anonymous", "restless", "mistyped", "declines-everything"],
)
async def test_a_broken_evaluator_fails_the_contract(broken: Scripted, message: str) -> None:
    with pytest.raises(ContractViolation, match=message):
        await check_evaluator(broken, INPUTS)


def labelled(name: str, start: int) -> Dataset[Thread, Helpfulness]:
    examples = [
        Example[Thread, Helpfulness](
            id=f"{name}-{i}",
            input=Thread(messages=[str(i % 4)]),
            verdict=judge(Thread(messages=[str(i % 4)])),
        )
        for i in range(start, start + 4)
    ]
    return Dataset(name, examples, input_type=Thread, verdict_type=Helpfulness)


async def test_best_of_meets_the_optimizer_contract() -> None:
    evaluator: Evaluator[Thread, Helpfulness] = scripted()
    await check_optimizer(
        BestOf([FunctionEvaluator(judge, verdict_type=Helpfulness)]),
        evaluator,
        train=labelled("train", 0),
        validate=labelled("validate", 10),
    )


class Meddling(BestOf[Thread, Helpfulness]):
    async def optimize(
        self,
        evaluator: Evaluator[Thread, Helpfulness],
        /,
        *,
        train: Dataset[Thread, Helpfulness],
        validate: Dataset[Thread, Helpfulness],
    ) -> Evaluator[Thread, Helpfulness]:
        if isinstance(evaluator, Scripted):
            evaluator.version = "meddled"
        return evaluator


class Switching(BestOf[Thread, Helpfulness]):
    async def optimize(
        self,
        evaluator: Evaluator[Thread, Helpfulness],
        /,
        *,
        train: Dataset[Thread, Helpfulness],
        validate: Dataset[Thread, Helpfulness],
    ) -> Evaluator[Thread, Helpfulness]:
        class Other(BaseModel):
            ok: bool = True

        other = FunctionEvaluator(lambda t: Other(), verdict_type=Other)
        return cast(Evaluator[Thread, Helpfulness], other)


@pytest.mark.parametrize(
    ("broken", "message"),
    [(Meddling([]), "must not change the evaluator"), (Switching([]), "same verdict type")],
    ids=["meddling", "switching"],
)
async def test_a_broken_optimizer_fails_the_contract(
    broken: BestOf[Thread, Helpfulness], message: str
) -> None:
    with pytest.raises(ContractViolation, match=message):
        await check_optimizer(
            broken, scripted(), train=labelled("train", 0), validate=labelled("validate", 10)
        )
