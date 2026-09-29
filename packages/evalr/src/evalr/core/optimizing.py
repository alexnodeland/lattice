"""Fitting an evaluator to people's verdicts, through the ``Optimizer`` port."""

from pydantic import BaseModel

from evalr.core.datasets import Dataset
from evalr.core.ports import Optimizer

__all__ = ["optimize"]


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
