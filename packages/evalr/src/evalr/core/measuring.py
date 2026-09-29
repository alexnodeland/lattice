"""Measuring an evaluator against people's verdicts on a dataset."""

import asyncio
from dataclasses import dataclass

from pydantic import BaseModel

from evalr.core.datasets import Dataset, Example
from evalr.core.metrics import (
    Agreement,
    EvaluatorStats,
    FieldCalibration,
    agreement,
    calibration,
    evaluator_stats,
)
from evalr.core.ports import Evaluator
from evalr.core.verdicts import Verdict

__all__ = ["Measurement", "measure"]


@dataclass(frozen=True, slots=True)
class Measurement[VerdictT: BaseModel]:
    """How an evaluator did on a dataset's labelled examples.

    Attributes:
        evaluator: The evaluator's name.
        version: Its version.
        dataset: The dataset's name.
        dataset_version: The dataset's content hash.
        verdicts: The verdicts it gave, by example id.
        errors: What went wrong where it gave none, by example id.
        agreement: Its agreement with people's verdicts.
        calibration: How well its confidence predicts being right, per field.
        stats: Latency and cost, per evaluator version that gave verdicts (a composition's
            verdicts come from more than one).
    """

    evaluator: str
    version: str
    dataset: str
    dataset_version: str
    verdicts: dict[str, Verdict[VerdictT]]
    errors: dict[str, str]
    agreement: Agreement
    calibration: dict[str, FieldCalibration]
    stats: list[EvaluatorStats]


async def measure[InputT: BaseModel, VerdictT: BaseModel](
    evaluator: Evaluator[InputT, VerdictT],
    dataset: Dataset[InputT, VerdictT],
    *,
    max_concurrency: int = 4,
) -> Measurement[VerdictT]:
    """Judge every labelled example of a dataset, and compare with people's verdicts.

    An example the evaluator fails on (or hands off) counts as a missing prediction.

    Args:
        evaluator: The evaluator to measure.
        dataset: Examples with people's verdicts; unlabelled ones are skipped.
        max_concurrency: How many examples are judged at once.
    """
    labelled = [e for e in dataset if e.verdict is not None]
    limit = asyncio.Semaphore(max_concurrency)

    async def judge(example: Example[InputT, VerdictT]) -> Verdict[VerdictT] | str:
        async with limit:
            try:
                return await evaluator.evaluate(example.input)
            except Exception as error:
                return f"{type(error).__name__}: {error}"

    outcomes = await asyncio.gather(*(judge(e) for e in labelled))
    verdicts = {e.id: o for e, o in zip(labelled, outcomes, strict=True) if isinstance(o, Verdict)}
    expected = [e.verdict for e in labelled if e.verdict is not None]
    given = [verdicts.get(e.id) for e in labelled]
    return Measurement(
        evaluator=evaluator.name,
        version=evaluator.version,
        dataset=dataset.name,
        dataset_version=dataset.version,
        verdicts=verdicts,
        errors={e.id: o for e, o in zip(labelled, outcomes, strict=True) if isinstance(o, str)},
        agreement=agreement(
            expected,
            [None if v is None else v.value for v in given],
            verdict_type=evaluator.verdict_type,
        ),
        calibration=calibration(expected, given, verdict_type=evaluator.verdict_type),
        stats=evaluator_stats(verdicts.values()),
    )
