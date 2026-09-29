"""Fitting an evaluator to people's verdicts, through the ``Optimizer`` port."""

from typing import Self

from pydantic import BaseModel, JsonValue

from evalr.core.datasets import Dataset
from evalr.core.ports import Optimizer

__all__ = ["DatasetRef", "Training", "optimize"]


class DatasetRef(BaseModel, frozen=True):
    """Which data was used: a dataset's name, content hash and size."""

    name: str
    version: str
    size: int

    @classmethod
    def of[InputT: BaseModel, VerdictT: BaseModel](cls, dataset: Dataset[InputT, VerdictT]) -> Self:
        """Refer to a dataset."""
        return cls(name=dataset.name, version=dataset.version, size=len(dataset))


class Training(BaseModel, frozen=True):
    """How a fitted evaluator was fitted, kept with it so its version can be explained.

    Attributes:
        optimizer: The optimizer's name, such as ``gepa`` or ``thresholds``.
        settings: The optimizer's settings, as JSON.
        base_version: The version of the evaluator it started from.
        train: The data it was fitted on.
        validation: The data it was checked on.
        score_before: Agreement with people on the validation data before fitting, from 0 to 1.
        score_after: Agreement after fitting.
    """

    optimizer: str
    settings: dict[str, JsonValue]
    base_version: str
    train: DatasetRef
    validation: DatasetRef
    score_before: float | None
    score_after: float | None


async def optimize[InputT: BaseModel, VerdictT: BaseModel, EvaluatorT](
    evaluator: EvaluatorT,
    *,
    train: Dataset[InputT, VerdictT],
    validate: Dataset[InputT, VerdictT],
    optimizer: Optimizer[InputT, VerdictT, EvaluatorT],
) -> EvaluatorT:
    """Fit an evaluator to people's verdicts with an optimizer.

    GEPA fits a DSPy judge; threshold calibration fits a decision evaluator. Only labelled
    examples are used, and no example may be in both sets, so the validation score is honest.

    Args:
        evaluator: The evaluator to start from. It is not changed.
        train: Examples to fit on.
        validate: Examples to check the fit on.
        optimizer: How to fit this kind of evaluator.

    Returns:
        The fitted evaluator, with a new version if it changed.

    Raises:
        ValueError: A set has no labelled examples, or the sets share an example.
    """
    train, validate = train.labelled(), validate.labelled()
    if not train or not validate:
        raise ValueError("optimizing needs labelled examples to train on and to validate on")
    shared = sorted({e.id for e in train} & {e.id for e in validate})
    if shared:
        raise ValueError(f"examples in both the training and validation sets: {shared[:5]}")
    return await optimizer.optimize(evaluator, train=train, validate=validate)
