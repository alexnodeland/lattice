"""Threshold calibration: fitting a decision evaluator's thresholds to people's verdicts.

A decision model is not trained; its thresholds are. pydantic-ai applies them on the client,
after the one request, so calibration asks the model once per example and then re-reads its
answers under every candidate threshold:

1. The boolean threshold (pydantic-ai's ``decision_boolean_threshold``) is the one at which the
   yes-or-no fields agree best with people on the training examples.
2. The hand-off threshold (``min_confidence``) is the lowest at which the evaluator agrees with
   people on at least ``target_agreement`` of what it keeps, handing off the rest; if none
   reaches the target, the one that agrees best.
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, JsonValue
from pydantic_ai.models.decision import DecisionHandOff

from evalr.core import Dataset, DatasetRef, Example, Training, agreement_score
from evalr.decision.evaluators import Decision, DecisionEvaluator

__all__ = ["DEFAULT_GRID", "ThresholdCalibration"]

DEFAULT_GRID = tuple(round(i / 20, 2) for i in range(1, 20))
"""Candidate thresholds: 0.05 to 0.95 in steps of 0.05."""


@dataclass(frozen=True, slots=True)
class _Observed[VerdictT: BaseModel]:
    expected: VerdictT
    decision: Decision[VerdictT]


@dataclass(frozen=True, slots=True)
class _Outcome:
    agreement: float | None
    coverage: float


class ThresholdCalibration:
    """Calibration as an ``Optimizer`` of decision evaluators.

    The fitted evaluator records a ``Training`` whose scores are its agreement with people on
    the validation examples it keeps, before and after, with the share it keeps (its coverage)
    in ``results``: a higher hand-off threshold keeps fewer examples, and the fallback judges
    the rest.
    """

    def __init__(
        self,
        *,
        target_agreement: float = 0.9,
        grid: Sequence[float] = DEFAULT_GRID,
        max_concurrency: int = 4,
    ) -> None:
        """Configure calibration.

        Args:
            target_agreement: The agreement with people, from 0 to 1, the evaluator should
                reach on what it keeps.
            grid: Candidate thresholds, each strictly between 0 and 1.
            max_concurrency: How many examples are asked at once.

        Raises:
            ValueError: The target or a candidate threshold is out of range.
        """
        if not 0.0 <= target_agreement <= 1.0:
            raise ValueError(f"target_agreement must be between 0 and 1; got {target_agreement}")
        if not grid or any(not 0.0 < t < 1.0 for t in grid):
            raise ValueError("grid must hold thresholds strictly between 0 and 1")
        self.target_agreement = target_agreement
        self.grid = tuple(sorted(set(grid)))
        self.max_concurrency = max_concurrency

    @property
    def settings(self) -> dict[str, JsonValue]:
        """The settings, as recorded on a calibrated evaluator."""
        return {"target_agreement": self.target_agreement, "grid": list(self.grid)}

    async def optimize[InputT: BaseModel, VerdictT: BaseModel](
        self,
        evaluator: DecisionEvaluator[InputT, VerdictT],
        /,
        *,
        train: Dataset[InputT, VerdictT],
        validate: Dataset[InputT, VerdictT],
    ) -> DecisionEvaluator[InputT, VerdictT]:
        """Fit the thresholds on ``train``, and measure before and after on ``validate``.

        Examples the model hands off whatever the thresholds (pydantic-ai's own hand-offs) are
        left out of the fitting.
        """
        fitting = await self._observe(evaluator, train)
        checking = await self._observe(evaluator, validate)
        boolean = self._boolean_threshold(fitting, evaluator.boolean_threshold)
        min_confidence = self._min_confidence(fitting, boolean)
        before = _outcome(checking, evaluator.boolean_threshold, evaluator.min_confidence)
        after = _outcome(checking, boolean, min_confidence)
        return evaluator.calibrated(
            boolean_threshold=boolean,
            min_confidence=min_confidence,
            training=Training(
                optimizer="thresholds",
                settings=self.settings,
                base_version=evaluator.version,
                train=DatasetRef.of(train),
                validation=DatasetRef.of(validate),
                score_before=before.agreement,
                score_after=after.agreement,
                results={
                    "boolean_threshold": boolean,
                    "min_confidence": min_confidence,
                    "coverage_before": before.coverage,
                    "coverage_after": after.coverage,
                },
            ),
        )

    async def _observe[InputT: BaseModel, VerdictT: BaseModel](
        self, evaluator: DecisionEvaluator[InputT, VerdictT], dataset: Dataset[InputT, VerdictT]
    ) -> list[_Observed[VerdictT]]:
        limit = asyncio.Semaphore(self.max_concurrency)

        async def ask(
            example: Example[InputT, VerdictT], expected: VerdictT
        ) -> _Observed[VerdictT] | None:
            async with limit:
                try:
                    decision = await evaluator.decide(example.input)
                except DecisionHandOff:
                    return None
            return _Observed(expected=expected, decision=decision)

        observed = await asyncio.gather(
            *(ask(e, e.verdict) for e in dataset if e.verdict is not None)
        )
        return [o for o in observed if o is not None]

    def _boolean_threshold[VerdictT: BaseModel](
        self, observed: list[_Observed[VerdictT]], current: float
    ) -> float:
        if not any(o.decision.probabilities for o in observed):
            return current
        return max(
            self.grid,
            key=lambda t: (_outcome(observed, t, None).agreement or 0.0, -abs(t - current), -t),
        )

    def _min_confidence[VerdictT: BaseModel](
        self, observed: list[_Observed[VerdictT]], boolean: float
    ) -> float | None:
        candidates: list[float | None] = [None, *self.grid]
        outcomes = [(m, _outcome(observed, boolean, m)) for m in candidates]
        kept = [(m, o.agreement) for m, o in outcomes if o.agreement is not None]
        for m, agreement in kept:
            if agreement >= self.target_agreement:
                return m
        best = max((agreement for _, agreement in kept), default=None)
        return next((m for m, agreement in kept if agreement == best), None)


def _rethreshold[VerdictT: BaseModel](
    decision: Decision[VerdictT], threshold: float
) -> tuple[VerdictT, dict[str, float]]:
    """A decision's value and confidence as they would be under another boolean threshold."""
    answers = {name: p >= threshold for name, p in decision.probabilities.items()}
    confidence = {
        **decision.confidence,
        **{name: p if answers[name] else 1 - p for name, p in decision.probabilities.items()},
    }
    return decision.value.model_copy(update=answers), confidence


def _outcome[VerdictT: BaseModel](
    observed: list[_Observed[VerdictT]], boolean: float, min_confidence: float | None
) -> _Outcome:
    """Agreement on the examples kept under these thresholds, and the share kept."""
    scores: list[float] = []
    kept = 0
    for o in observed:
        value, confidence = _rethreshold(o.decision, boolean)
        if min_confidence is not None and confidence and min(confidence.values()) < min_confidence:
            continue
        kept += 1
        score = agreement_score(o.expected, value)
        if score is not None:
            scores.append(score)
    return _Outcome(
        agreement=sum(scores) / len(scores) if scores else None,
        coverage=kept / len(observed) if observed else 0.0,
    )
