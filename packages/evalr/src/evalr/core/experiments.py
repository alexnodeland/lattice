"""Experiments: a task run over a dataset, with every output judged."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel

from evalr.core.datasets import Example
from evalr.core.verdicts import Verdict

__all__ = ["ExperimentResult", "ItemResult", "Task"]

type Task[InputT: BaseModel, VerdictT: BaseModel, OutputT: BaseModel] = Callable[
    [Example[InputT, VerdictT]], Awaitable[OutputT]
]
"""What an experiment runs for each example: the system being evaluated, producing an output.

The output is what the experiment's evaluators judge, so it holds whatever they need, such as the
request and the new reply. A task that judges the example's input as it is (to measure an
evaluator against people's verdicts) returns the input.
"""


@dataclass(frozen=True, slots=True)
class ItemResult[OutputT: BaseModel]:
    """What happened to one example in an experiment.

    Attributes:
        example_id: The example's id.
        output: The task's output, or ``None`` when the task failed.
        verdicts: One verdict per evaluator that succeeded, in the evaluators' order.
        errors: What failed: the task, or an evaluator by name, with its message.
        trace_id: The trace the example ran in, when there was one.
    """

    example_id: str
    output: OutputT | None
    verdicts: tuple[Verdict[BaseModel], ...] = ()
    errors: tuple[str, ...] = ()
    trace_id: str | None = None


@dataclass(frozen=True, slots=True)
class ExperimentResult[OutputT: BaseModel]:
    """An experiment's results: one item per example of the dataset, in the dataset's order.

    Attributes:
        name: The experiment's name, shared by its runs.
        run_name: This run's name.
        dataset: The dataset's name.
        dataset_version: The dataset's content hash.
        items: One result per example.
        url: Where the tracker shows the run, when it has a UI.
    """

    name: str
    run_name: str
    dataset: str
    dataset_version: str
    items: tuple[ItemResult[OutputT], ...]
    url: str | None = None

    def verdicts(self, evaluator: str) -> dict[str, Verdict[BaseModel]]:
        """One evaluator's verdicts, by example id."""
        return {
            item.example_id: verdict
            for item in self.items
            for verdict in item.verdicts
            if verdict.evaluator == evaluator
        }
