"""Every experiment tracker adapter meets the ExperimentTracker contract."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any, cast

import pytest
from pydantic import BaseModel

from evalr.contracts import ContractViolation, check_experiment_tracker
from evalr.core import Dataset, Evaluator, ExperimentResult, Task
from evalr.memory import InMemoryExperimentTracker

from ..conftest import Spans

type Rewrite = Callable[[ExperimentResult[Any]], ExperimentResult[Any]]


async def test_the_in_memory_tracker_meets_the_contract() -> None:
    await check_experiment_tracker(InMemoryExperimentTracker())


async def test_the_in_memory_tracker_meets_the_contract_with_traces(spans: Spans) -> None:
    await check_experiment_tracker(InMemoryExperimentTracker(tracer_provider=spans.provider))


class Rewriting(InMemoryExperimentTracker):
    """Breaks its results after a correct run."""

    def __init__(self, rewrite: Rewrite) -> None:
        super().__init__()
        self.rewrite = rewrite

    async def run_experiment[I: BaseModel, V: BaseModel, O: BaseModel](
        self,
        name: str,
        /,
        *,
        dataset: Dataset[I, V],
        task: Task[I, V, O],
        evaluators: Sequence[Evaluator[O, BaseModel]],
        run_name: str | None = None,
        max_concurrency: int = 4,
        metadata: Mapping[str, str] | None = None,
    ) -> ExperimentResult[O]:
        result = await super().run_experiment(
            name,
            dataset=dataset,
            task=task,
            evaluators=evaluators,
            run_name=run_name,
            max_concurrency=max_concurrency,
            metadata=metadata,
        )
        return cast(ExperimentResult[O], self.rewrite(result))


BROKEN: dict[str, tuple[Rewrite, str]] = {
    "run-name": (lambda r: replace(r, run_name="other"), "names must be kept"),
    "dataset-version": (
        lambda r: replace(r, dataset_version="0"),
        "name the dataset and its version",
    ),
    "dropped-items": (
        lambda r: replace(r, items=tuple(i for i in r.items if i.output is not None)),
        "one item per example",
    ),
    "hidden-errors": (
        lambda r: replace(
            r, items=tuple(replace(i, errors=()) if i.output is None else i for i in r.items)
        ),
        "must leave no output and record its error",
    ),
    "lost-outputs": (
        lambda r: replace(r, items=tuple(replace(i, output=r.items[0].output) for i in r.items)),
        "output must be kept",
    ),
    "untraced-verdicts": (
        lambda r: replace(r, items=tuple(replace(i, trace_id="f" * 32) for i in r.items)),
        "must leave no output|must record the item's trace",
    ),
}


@pytest.mark.parametrize("case", sorted(BROKEN))
async def test_a_broken_tracker_fails_the_contract(case: str) -> None:
    rewrite, message = BROKEN[case]
    with pytest.raises(ContractViolation, match=message):
        await check_experiment_tracker(Rewriting(rewrite))


def _errors_only_on_the_failed_task(r: ExperimentResult[Any]) -> ExperimentResult[Any]:
    items = tuple(
        replace(i, errors=("picky: invented",)) if i.example_id == "example-0" else i
        for i in r.items
    )
    return replace(r, items=items)


async def test_errors_where_nothing_failed_fail_the_contract() -> None:
    with pytest.raises(ContractViolation, match="nothing failed, so no errors"):
        await check_experiment_tracker(Rewriting(_errors_only_on_the_failed_task))


def _drop_evaluator_errors(r: ExperimentResult[Any]) -> ExperimentResult[Any]:
    return replace(
        r,
        items=tuple(replace(i, errors=()) if i.output is not None else i for i in r.items),
    )


async def test_hidden_evaluator_errors_fail_the_contract() -> None:
    with pytest.raises(ContractViolation, match="a failed evaluator must record its error"):
        await check_experiment_tracker(Rewriting(_drop_evaluator_errors))
