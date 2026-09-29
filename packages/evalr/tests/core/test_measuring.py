import pytest

from evalr import Dataset, Example, FunctionEvaluator, measure, optimize
from evalr.memory import BestOf

from .models import Helpfulness, Scripted, Thread

Ex = Example[Thread, Helpfulness]


def dataset(name: str = "d", start: int = 0) -> Dataset[Thread, Helpfulness]:
    examples = [
        Ex(
            id=f"{name}-{i}",
            input=Thread(messages=[str(i)]),
            verdict=Helpfulness(rating=1 + i % 5, resolved=i % 2 == 0) if i != 5 else None,
        )
        for i in range(start, start + 6)
    ]
    return Dataset(name, examples, input_type=Thread, verdict_type=Helpfulness)


def perfect(thread: Thread) -> Helpfulness:
    i = int(thread.messages[0])
    return Helpfulness(rating=1 + i % 5, resolved=i % 2 == 0)


def always_five(thread: Thread) -> Helpfulness:
    if thread.messages[0] == "3":
        raise RuntimeError("cannot judge 3")
    return Helpfulness(rating=5, resolved=True)


async def test_measure_compares_an_evaluator_with_people() -> None:
    data = dataset()
    result = await measure(FunctionEvaluator(always_five, verdict_type=Helpfulness), data)
    assert (result.evaluator, result.version, result.dataset) == ("always_five", "1", "d")
    assert result.dataset_version == data.version
    assert set(result.verdicts) == {"d-0", "d-1", "d-2", "d-4"}
    assert result.errors == {"d-3": "RuntimeError: cannot judge 3"}
    assert result.agreement.n == 5
    assert result.agreement.fields["rating"].missing == 1
    assert [s.n for s in result.stats] == [4]
    assert result.calibration == {}


async def test_measure_reads_confidence() -> None:
    scripted = Scripted(
        {"0": (Helpfulness(rating=1, resolved=True), {"resolved": 0.8})},
    )
    data = dataset().filter(lambda e: e.id == "d-0")
    result = await measure(scripted, data)
    assert result.agreement.score == 1.0
    assert result.calibration["resolved"].brier_score == pytest.approx(0.04)


async def test_best_of_picks_on_training_and_checks_on_validation() -> None:
    weak = FunctionEvaluator(always_five, verdict_type=Helpfulness)
    strong = FunctionEvaluator(perfect, verdict_type=Helpfulness)
    optimizer = BestOf([strong])
    chosen = await optimize(
        weak, train=dataset("train"), validate=dataset("validate", 10), optimizer=optimizer
    )
    assert chosen is strong
    assert [(m.evaluator, m.dataset) for m in optimizer.measurements] == [
        ("always_five", "train"),
        ("perfect", "train"),
        ("perfect", "validate"),
    ]


async def test_best_of_keeps_the_given_evaluator_on_a_tie() -> None:
    first = FunctionEvaluator(perfect, verdict_type=Helpfulness)
    same = FunctionEvaluator(perfect, verdict_type=Helpfulness, name="copy")
    chosen = await optimize(
        first, train=dataset("train"), validate=dataset("validate", 10), optimizer=BestOf([same])
    )
    assert chosen is first


async def test_a_small_dataset_is_measured_until_it_can_be_split() -> None:
    few = dataset().filter(lambda e: e.id in {"d-0", "d-1"})
    train, validate = few.labelled().split(0.2)
    evaluator = FunctionEvaluator(perfect, verdict_type=Helpfulness)
    with pytest.raises(
        ValueError,
        match=r"has 2 to train on and 0 to validate on: a small dataset can split with nothing on "
        r"one side\. Until there are enough to split, measure the evaluator on all of them instead",
    ):
        await optimize(evaluator, train=train, validate=validate, optimizer=BestOf([]))
    assert (await measure(evaluator, few)).agreement.score == 1.0


async def test_optimize_refuses_shared_examples() -> None:
    evaluator = FunctionEvaluator(perfect, verdict_type=Helpfulness)
    with pytest.raises(ValueError, match=r"in both the training and validation sets: \['d-0'"):
        await optimize(evaluator, train=dataset(), validate=dataset(), optimizer=BestOf([]))
