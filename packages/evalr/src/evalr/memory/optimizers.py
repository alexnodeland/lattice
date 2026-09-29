"""An optimizer that selects the best of several evaluators."""

from collections.abc import Sequence

from pydantic import BaseModel

from evalr.core import Dataset, Evaluator, Measurement, measure

__all__ = ["BestOf"]


class BestOf[InputT: BaseModel, VerdictT: BaseModel]:
    """Picks the evaluator that agrees best with people on the training set.

    It works for any kind of evaluator, and trains nothing: it measures the evaluator it is
    given and each candidate on ``train``, keeps the best, and measures that one on
    ``validate``. A tie keeps the earlier, so the evaluator given wins unless a candidate is
    strictly better.

    Attributes:
        measurements: Every measurement taken, in order; the last is the choice on ``validate``.
    """

    def __init__(
        self, candidates: Sequence[Evaluator[InputT, VerdictT]], *, max_concurrency: int = 4
    ) -> None:
        """Hold the candidates.

        Args:
            candidates: The evaluators to compare with the one being optimized.
            max_concurrency: How many examples are judged at once.
        """
        self.candidates = tuple(candidates)
        self.max_concurrency = max_concurrency
        self.measurements: list[Measurement[VerdictT]] = []

    async def optimize(
        self,
        evaluator: Evaluator[InputT, VerdictT],
        /,
        *,
        train: Dataset[InputT, VerdictT],
        validate: Dataset[InputT, VerdictT],
    ) -> Evaluator[InputT, VerdictT]:
        """Return whichever of the evaluator and the candidates scores best on ``train``."""
        best, best_score = evaluator, -1.0
        for candidate in (evaluator, *self.candidates):
            score = (await self._measure(candidate, train)).agreement.score or 0.0
            if score > best_score:
                best, best_score = candidate, score
        await self._measure(best, validate)
        return best

    async def _measure(
        self, evaluator: Evaluator[InputT, VerdictT], dataset: Dataset[InputT, VerdictT]
    ) -> Measurement[VerdictT]:
        measurement = await measure(evaluator, dataset, max_concurrency=self.max_concurrency)
        self.measurements.append(measurement)
        return measurement
