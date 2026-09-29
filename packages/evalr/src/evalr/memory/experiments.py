"""An experiment tracker that runs in the process and keeps its results in memory."""

import asyncio
from collections import Counter
from collections.abc import Mapping, Sequence

from opentelemetry import trace
from pydantic import BaseModel

from evalr.core import (
    Dataset,
    Evaluator,
    Example,
    ExperimentResult,
    ItemResult,
    Task,
    Verdict,
    current_trace_id,
    get_tracer,
)

__all__ = ["InMemoryExperimentTracker"]


class InMemoryExperimentTracker:
    """Runs experiments in the process, each example in its own span, and keeps every run.

    Attributes:
        runs: Every run so far, oldest first.
    """

    def __init__(self, *, tracer_provider: trace.TracerProvider | None = None) -> None:
        """Start with no runs.

        Args:
            tracer_provider: Where the examples' spans go; the global provider by default.
        """
        self.runs: list[ExperimentResult[BaseModel]] = []
        self._tracer = get_tracer(tracer_provider)
        self._counts: Counter[str] = Counter()

    async def run_experiment[InputT: BaseModel, VerdictT: BaseModel, OutputT: BaseModel](
        self,
        name: str,
        /,
        *,
        dataset: Dataset[InputT, VerdictT],
        task: Task[InputT, VerdictT, OutputT],
        evaluators: Sequence[Evaluator[OutputT, BaseModel]],
        run_name: str | None = None,
        max_concurrency: int = 4,
        metadata: Mapping[str, str] | None = None,
    ) -> ExperimentResult[OutputT]:
        """Run the task on every example, and judge each output with every evaluator.

        A run is named ``{name} #{n}`` by default, counting this tracker's runs of the
        experiment. Each example runs in a span named ``evalr.experiment.item {name}``.
        """
        self._counts[name] += 1
        limit = asyncio.Semaphore(max_concurrency)
        attributes = {f"evalr.experiment.metadata.{k}": v for k, v in (metadata or {}).items()}

        async def run(example: Example[InputT, VerdictT]) -> ItemResult[OutputT]:
            async with limit:
                with self._tracer.start_as_current_span(
                    f"evalr.experiment.item {name}",
                    attributes={
                        "evalr.experiment.name": name,
                        "evalr.example.id": example.id,
                        **attributes,
                    },
                ):
                    return await _item(example, task, evaluators)

        items = await asyncio.gather(*(run(example) for example in dataset))
        result = ExperimentResult(
            name=name,
            run_name=run_name or f"{name} #{self._counts[name]}",
            dataset=dataset.name,
            dataset_version=dataset.version,
            items=tuple(items),
        )
        self.runs.append(result)
        return result


async def _item[InputT: BaseModel, VerdictT: BaseModel, OutputT: BaseModel](
    example: Example[InputT, VerdictT],
    task: Task[InputT, VerdictT, OutputT],
    evaluators: Sequence[Evaluator[OutputT, BaseModel]],
) -> ItemResult[OutputT]:
    trace_id = current_trace_id()
    try:
        output = await task(example)
    except Exception as error:
        return ItemResult(example.id, None, errors=(_describe("task", error),), trace_id=trace_id)
    verdicts: list[Verdict[BaseModel]] = []
    errors: list[str] = []
    for evaluator in evaluators:
        try:
            verdicts.append(await evaluator.evaluate(output))
        except Exception as error:
            errors.append(_describe(evaluator.name, error))
    return ItemResult(example.id, output, tuple(verdicts), tuple(errors), trace_id)


def _describe(what: str, error: Exception) -> str:
    return f"{what}: {type(error).__name__}: {error}"
