"""Experiments: a task run over a dataset, with every output judged."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import overload

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


@dataclass(frozen=True)
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


@dataclass(frozen=True)
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

    @overload
    def verdicts(self, evaluator: str) -> dict[str, Verdict[BaseModel]]: ...

    @overload
    def verdicts[V: BaseModel](
        self, evaluator: str, *, verdict_type: type[V]
    ) -> dict[str, Verdict[V]]: ...

    def verdicts(
        self, evaluator: str, *, verdict_type: type[BaseModel] = BaseModel
    ) -> Mapping[str, Verdict[BaseModel]]:
        """One evaluator's verdicts, by example id.

        An experiment can have evaluators of several verdict types, so verdicts are typed as
        ``BaseModel`` unless the evaluator's type is given:

        ```python
        verdicts = result.verdicts("helpfulness-judge", verdict_type=Helpfulness)
        ratings = [verdict.value.rating for verdict in verdicts.values()]
        ```

        Args:
            evaluator: The evaluator's name, as its verdicts record it.
            verdict_type: The verdict type it gives. Each verdict is checked to be one.

        Raises:
            TypeError: One of the evaluator's verdicts is not of ``verdict_type``.
        """
        found = {
            item.example_id: verdict
            for item in self.items
            for verdict in item.verdicts
            if verdict.evaluator == evaluator
        }
        for example_id, verdict in found.items():
            if not isinstance(verdict.value, verdict_type):
                raise TypeError(
                    f"{evaluator} gave {example_id} a verdict of type "
                    f"{type(verdict.value).__name__}, not {verdict_type.__name__}"
                )
        return found
