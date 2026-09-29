"""Langfuse experiments as an ``ExperimentTracker``.

The experiment runs through Langfuse's experiment API (``Langfuse.run_experiment``): each example
is an item with its own trace, the task runs in the item's task span, and each evaluator's
verdict becomes the item's scores. The SDK runs the experiment on an event loop of its own, in a
worker thread; evalr runs the task and the evaluators back on the caller's event loop, where
their clients live, inside the item's spans.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from langfuse import Evaluation, Langfuse
from langfuse.experiment import EvaluatorFunction, LocalExperimentItem
from opentelemetry import context
from pydantic import BaseModel

from evalr.core import (
    Dataset,
    Evaluator,
    ExperimentResult,
    ItemResult,
    Task,
    Verdict,
    current_trace_id,
    scores,
)
from evalr.core._explanation import explanation

__all__ = ["LangfuseExperimentTracker"]

_EVALR = "evalr"


class LangfuseExperimentTracker:
    """Runs experiments in Langfuse, where they show beside the traces of each item.

    Each example's task and evaluators run in the item's trace, so the spans of whatever they
    call nest under it, and each verdict records it. Text fields, which Langfuse's evaluations
    cannot hold, become the comment of the verdict's other scores.
    """

    def __init__(
        self, client: Langfuse, *, type_names: Mapping[type[BaseModel], str] | None = None
    ) -> None:
        """Use a Langfuse client.

        Args:
            client: The application's client.
            type_names: Score names for verdict types, where a library registers its feedback
                under a name other than the class name in snake case, so that evaluators' scores
                and people's line up.
        """
        self.client = client
        self.type_names = dict(type_names or {})

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
        """Run the task on every example in Langfuse, and judge each output.

        A run is named by Langfuse (``{name} - {time}``) unless named.
        """
        here = _Bridge(asyncio.get_running_loop())
        examples = {example.id: example for example in dataset}
        outputs: dict[str, OutputT] = {}
        traces: dict[str, str | None] = {}
        verdicts: dict[str, dict[int, Verdict[BaseModel]]] = {e: {} for e in examples}
        errors: dict[str, list[str]] = {e: [] for e in examples}

        async def run_task(*, item: Any, **_: object) -> OutputT:
            example = examples[_example_id(item["metadata"])]
            traces[example.id] = current_trace_id()
            try:
                output = await here.run(task, example)
            except Exception as error:
                errors[example.id].append(_describe("task", error))
                raise
            outputs[example.id] = output
            return output

        def judge(index: int, evaluator: Evaluator[OutputT, BaseModel]) -> EvaluatorFunction:
            async def evaluate(
                *, output: OutputT, metadata: dict[str, Any] | None, **_: object
            ) -> list[Evaluation]:
                example_id = _example_id(metadata)
                try:
                    verdict = await here.run(evaluator.evaluate, output)
                except Exception as error:
                    errors[example_id].append(_describe(evaluator.name, error))
                    raise
                verdicts[example_id][index] = verdict
                return evaluations(verdict, type_name=self.type_names.get(type(verdict.value)))

            evaluate.__name__ = evaluator.name
            return evaluate

        data = [
            LocalExperimentItem(
                input=example.input.model_dump(mode="json"),
                expected_output={
                    "verdict": example.verdict and example.verdict.model_dump(mode="json"),
                    "reference": example.reference,
                },
                metadata={**example.metadata, _EVALR: {"example_id": example.id}},
            )
            for example in dataset
        ]
        result = await asyncio.to_thread(
            self.client.run_experiment,
            name=name,
            run_name=run_name,
            data=data,
            task=run_task,
            evaluators=[judge(i, e) for i, e in enumerate(evaluators)],
            max_concurrency=max_concurrency,
            metadata=dict(metadata or {}),
        )
        return ExperimentResult(
            name=name,
            run_name=result.run_name,
            dataset=dataset.name,
            dataset_version=dataset.version,
            items=tuple(
                ItemResult(
                    example_id=e,
                    output=outputs.get(e),
                    verdicts=tuple(verdicts[e][i] for i in sorted(verdicts[e])),
                    errors=tuple(errors[e]),
                    trace_id=traces.get(e),
                )
                for e in examples
            ),
            url=result.dataset_run_url,
        )


def evaluations(verdict: Verdict[BaseModel], *, type_name: str | None = None) -> list[Evaluation]:
    """A verdict as Langfuse evaluations: one per field that is not text, named ``{type}.{field}``.

    Langfuse's evaluations hold numbers, booleans and categories only, so the verdict's text
    fields (people's or the judge's reasons) become each evaluation's comment.

    Args:
        verdict: The verdict.
        type_name: The ``{type}`` in the evaluations' names, as ``scores`` takes it.
    """
    judged = scores(verdict, type_name=type_name)
    comment = explanation(judged) or None
    return [
        Evaluation(
            name=score.name,
            value=score.value,
            comment=comment,
            metadata=score.metadata,
            data_type=score.data_type,
        )
        for score in judged
        if score.data_type != "TEXT"
    ]


class _Bridge:
    """Runs coroutines on the caller's event loop from the SDK's, keeping the trace context."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    async def run[T, A](self, function: Callable[[A], Awaitable[T]], argument: A) -> T:
        caller = context.get_current()

        async def inside() -> T:
            token = context.attach(caller)
            try:
                return await function(argument)
            finally:
                context.detach(token)

        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(inside(), self.loop))


def _example_id(metadata: Mapping[str, Any] | None) -> str:
    ours: Any = (metadata or {})[_EVALR]
    return str(ours["example_id"])


def _describe(what: str, error: Exception) -> str:
    return f"{what}: {type(error).__name__}: {error}"
