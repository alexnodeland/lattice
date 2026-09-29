"""Agreement and calibration metrics: how far to trust an evaluator.

Agreement compares an evaluator's verdicts with people's, field by field, with the measures that
suit each field's kind:

- binary and categorical fields: accuracy and Cohen's kappa
- ordinal and numeric fields: mean absolute error and Spearman's rank correlation

Calibration asks whether an evaluator's confidence means what it says: expected calibration
error and the Brier score. A verdict's confidence is one probability per field (that the field's
value is right), so both are top-label measures: the confidence in the value given, against
whether it was right.

A measure that is undefined for its data (no pairs, or kappa or Spearman when a side never
varies) is ``None`` rather than NaN, so results compare and serialize cleanly.
"""

import math
from collections import Counter
from collections.abc import Hashable, Iterable, Sequence
from itertools import groupby
from typing import cast

from pydantic import BaseModel

from evalr.core.fields import FieldKind, VerdictField, verdict_fields
from evalr.core.verdicts import Verdict

__all__ = [
    "Agreement",
    "EvaluatorStats",
    "FieldAgreement",
    "FieldCalibration",
    "accuracy",
    "agreement",
    "agreement_score",
    "brier_score",
    "calibration",
    "cohen_kappa",
    "evaluator_stats",
    "expected_calibration_error",
    "field_agreement",
    "mean_absolute_error",
    "spearman",
]

_CATEGORIES = (FieldKind.BINARY, FieldKind.CATEGORICAL)


# ─── measures over paired values ──────────────────────────────────────────────


def accuracy(expected: Sequence[Hashable], predicted: Sequence[Hashable]) -> float | None:
    """The share of pairs that are equal; ``None`` for no pairs."""
    n = _paired(expected, predicted)
    return sum(e == p for e, p in zip(expected, predicted, strict=True)) / n if n else None


def cohen_kappa(expected: Sequence[Hashable], predicted: Sequence[Hashable]) -> float | None:
    """Cohen's kappa: agreement beyond what the two sides' label frequencies give by chance.

    1 is perfect agreement and 0 is chance. ``None`` for no pairs, or when chance agreement is
    already perfect (both sides always give the one same label).
    """
    n = _paired(expected, predicted)
    agree = sum(e == p for e, p in zip(expected, predicted, strict=True))
    counted = Counter(predicted)
    chance = sum(count * counted[label] for label, count in Counter(expected).items())
    if n * n == chance:
        return None
    return (agree * n - chance) / (n * n - chance)


def mean_absolute_error(expected: Sequence[float], predicted: Sequence[float]) -> float | None:
    """The mean absolute difference between pairs; ``None`` for no pairs."""
    n = _paired(expected, predicted)
    return sum(abs(e - p) for e, p in zip(expected, predicted, strict=True)) / n if n else None


def spearman(expected: Sequence[float], predicted: Sequence[float]) -> float | None:
    """Spearman's rank correlation, with tied values given their average rank.

    ``None`` for fewer than two pairs, or when either side is constant.
    """
    n = _paired(expected, predicted)
    if n < 2:
        return None
    x, y = _ranks(expected), _ranks(predicted)
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return None
    return max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy)))


def brier_score(confidences: Sequence[float], correct: Sequence[bool]) -> float | None:
    """The mean squared difference between confidence and correctness; ``None`` for no pairs.

    0 is perfect; always answering with confidence 0.5 scores 0.25.
    """
    n = _probabilities(confidences, correct)
    return sum((c - ok) ** 2 for c, ok in zip(confidences, correct, strict=True)) / n if n else None


def expected_calibration_error(
    confidences: Sequence[float], correct: Sequence[bool], *, bins: int = 10
) -> float | None:
    """The gap between confidence and accuracy, averaged over bins of equal width.

    Confidences fall into ``bins`` intervals of ``[0, 1]``, each closed below and open above,
    except the last, which includes 1. The result weights each bin's gap between its mean
    confidence and its accuracy by its share of the pairs. ``None`` for no pairs.

    Raises:
        ValueError: ``bins`` is less than 1, or a confidence is outside ``[0, 1]``.
    """
    if bins < 1:
        raise ValueError(f"bins must be at least 1; got {bins}")
    n = _probabilities(confidences, correct)
    if not n:
        return None
    total = [0.0] * bins
    right = [0] * bins
    count = [0] * bins
    for c, ok in zip(confidences, correct, strict=True):
        b = min(int(c * bins), bins - 1)
        total[b] += c
        right[b] += ok
        count[b] += 1
    return sum(abs(right[b] - total[b]) / n for b in range(bins) if count[b])


def _paired(expected: Sequence[object], predicted: Sequence[object]) -> int:
    if len(expected) != len(predicted):
        raise ValueError(f"{len(expected)} expected values but {len(predicted)} predicted")
    return len(expected)


def _probabilities(confidences: Sequence[float], correct: Sequence[bool]) -> int:
    n = _paired(confidences, correct)
    if any(not 0.0 <= c <= 1.0 for c in confidences):
        raise ValueError("confidences must be between 0 and 1")
    return n


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    for _, group in groupby(order, key=values.__getitem__):
        members = list(group)
        average = start + (len(members) + 1) / 2
        for i in members:
            ranks[i] = average
        start += len(members)
    return ranks


# ─── agreement between verdicts ───────────────────────────────────────────────


def field_agreement[V: BaseModel](expected: V, predicted: V | None) -> dict[str, float]:
    """How far a predicted verdict agrees with the expected one, per compared field, from 0 to 1.

    Only fields with an expected value count. Binary and categorical fields agree fully or not
    at all. Ordinal and bounded numeric fields lose agreement in proportion to the distance
    over their range (``1 - |e - p| / (upper - lower)``); unbounded ones as ``1 / (1 + |e - p|)``.
    A missing prediction (the whole verdict, or the field) agrees not at all.
    """
    result: dict[str, float] = {}
    for field in verdict_fields(type(expected)):
        value: object = getattr(expected, field.name)
        if field.compared and value is not None:
            other: object = None if predicted is None else getattr(predicted, field.name)
            result[field.name] = _agreement(field, value, other)
    return result


def agreement_score[V: BaseModel](expected: V, predicted: V | None) -> float | None:
    """The mean of ``field_agreement``: one number from 0 to 1 per pair of verdicts.

    ``None`` when the expected verdict has no compared field with a value.
    """
    values = field_agreement(expected, predicted).values()
    return sum(values) / len(values) if values else None


def _agreement(field: VerdictField, expected: object, predicted: object) -> float:
    if predicted is None:
        return 0.0
    if field.kind in _CATEGORIES:
        return float(expected == predicted)
    difference = abs(_float(expected) - _float(predicted))
    if field.lower is not None and field.upper is not None and field.upper > field.lower:
        return max(0.0, 1.0 - difference / (field.upper - field.lower))
    return 1.0 / (1.0 + difference)


def _float(value: object) -> float:
    return float(cast(float, value))


class FieldAgreement(BaseModel, frozen=True):
    """Agreement on one field, over the pairs whose expected value is set.

    Attributes:
        field: The field's name.
        kind: The field's kind, which decides the measures.
        n: Pairs whose expected value is set.
        missing: Of those, pairs with no predicted value.
        score: The mean of the per-pair agreement, from 0 to 1.
        accuracy: For binary and categorical fields; a missing prediction is wrong.
        kappa: Cohen's kappa, for binary and categorical fields.
        mean_absolute_error: For ordinal and numeric fields, over the pairs with a prediction.
        spearman: Spearman's rank correlation, likewise.
    """

    field: str
    kind: FieldKind
    n: int
    missing: int
    score: float | None
    accuracy: float | None = None
    kappa: float | None = None
    mean_absolute_error: float | None = None
    spearman: float | None = None


class Agreement(BaseModel, frozen=True):
    """How far an evaluator agrees with people over a set of verdicts.

    Attributes:
        n: The pairs compared.
        score: The mean ``agreement_score`` over pairs that have one, from 0 to 1.
        fields: Per compared field, in the verdict type's order.
    """

    n: int
    score: float | None
    fields: dict[str, FieldAgreement]


def agreement[V: BaseModel](
    expected: Sequence[V], predicted: Sequence[V | None], *, verdict_type: type[V]
) -> Agreement:
    """Compare predicted verdicts with the expected ones, pair by pair.

    Args:
        expected: People's verdicts.
        predicted: The evaluator's verdicts for the same inputs, in the same order; ``None``
            where it gave none.
        verdict_type: The verdict type, whose fields are compared.

    Raises:
        ValueError: The sequences differ in length.
    """
    _paired(expected, predicted)
    fields: dict[str, FieldAgreement] = {}
    for field in verdict_fields(verdict_type):
        if field.compared:
            fields[field.name] = _field_agreement(field, expected, predicted)
    per_pair = [agreement_score(e, p) for e, p in zip(expected, predicted, strict=True)]
    scored = [s for s in per_pair if s is not None]
    return Agreement(
        n=len(expected),
        score=sum(scored) / len(scored) if scored else None,
        fields=fields,
    )


def _field_agreement[V: BaseModel](
    field: VerdictField, expected: Sequence[V], predicted: Sequence[V | None]
) -> FieldAgreement:
    pairs: list[tuple[object, object]] = []
    for e, p in zip(expected, predicted, strict=True):
        value: object = getattr(e, field.name)
        if value is not None:
            pairs.append((value, None if p is None else getattr(p, field.name)))
    n = len(pairs)
    agreements = [_agreement(field, e, p) for e, p in pairs]
    categorical = field.kind in _CATEGORIES
    labels = (
        cast(list[Hashable], [e for e, _ in pairs]),
        cast(list[Hashable], [p for _, p in pairs]),
    )
    present = [(_float(e), _float(p)) for e, p in pairs if p is not None and not categorical]
    xs, ys = [e for e, _ in present], [p for _, p in present]
    return FieldAgreement(
        field=field.name,
        kind=field.kind,
        n=n,
        missing=sum(p is None for _, p in pairs),
        score=sum(agreements) / n if n else None,
        accuracy=accuracy(*labels) if categorical else None,
        kappa=cohen_kappa(*labels) if categorical else None,
        mean_absolute_error=None if categorical else mean_absolute_error(xs, ys),
        spearman=None if categorical else spearman(xs, ys),
    )


# ─── calibration ──────────────────────────────────────────────────────────────


class FieldCalibration(BaseModel, frozen=True):
    """Calibration of one field's confidence, over the pairs that have one.

    Attributes:
        field: The field's name.
        n: Pairs with an expected value and a confidence.
        accuracy: The share of those whose predicted value was right.
        confidence: The mean confidence.
        expected_calibration_error: See ``expected_calibration_error``.
        brier_score: See ``brier_score``.
    """

    field: str
    n: int
    accuracy: float | None
    confidence: float | None
    expected_calibration_error: float | None
    brier_score: float | None


def calibration[V: BaseModel](
    expected: Sequence[V],
    verdicts: Sequence[Verdict[V] | None],
    *,
    verdict_type: type[V],
    bins: int = 10,
) -> dict[str, FieldCalibration]:
    """Measure how well each field's confidence predicts that its value is right.

    Args:
        expected: People's verdicts.
        verdicts: The evaluator's verdicts for the same inputs, in the same order; ``None``
            where it gave none.
        verdict_type: The verdict type, whose fields are measured.
        bins: The bins of the expected calibration error.

    Returns:
        One entry per field that any verdict has a confidence for, in the verdict type's order.

    Raises:
        ValueError: The sequences differ in length.
    """
    _paired(expected, verdicts)
    confidences: dict[str, list[float]] = {}
    correct: dict[str, list[bool]] = {}
    for e, v in zip(expected, verdicts, strict=True):
        if v is None:
            continue
        for name, confidence in v.confidence.items():
            value: object = getattr(e, name)
            if value is not None:
                confidences.setdefault(name, []).append(confidence)
                correct.setdefault(name, []).append(getattr(v.value, name) == value)
    return {
        name: FieldCalibration(
            field=name,
            n=len(confidences[name]),
            accuracy=sum(correct[name]) / len(correct[name]),
            confidence=sum(confidences[name]) / len(confidences[name]),
            expected_calibration_error=expected_calibration_error(
                confidences[name], correct[name], bins=bins
            ),
            brier_score=brier_score(confidences[name], correct[name]),
        )
        for name in (f.name for f in verdict_fields(verdict_type))
        if name in confidences
    }


# ─── cost and latency ─────────────────────────────────────────────────────────


class EvaluatorStats(BaseModel, frozen=True):
    """Latency and cost of one version of one evaluator.

    Attributes:
        evaluator: The evaluator's name.
        version: Its version.
        n: Verdicts measured.
        mean_latency: Mean seconds per verdict.
        p50_latency: Median seconds, by nearest rank.
        p95_latency: 95th percentile seconds, by nearest rank.
        total_cost: US dollars over the verdicts that report a cost; ``None`` if none do.
        mean_cost: The mean over those verdicts.
    """

    evaluator: str
    version: str
    n: int
    mean_latency: float
    p50_latency: float
    p95_latency: float
    total_cost: float | None
    mean_cost: float | None


def evaluator_stats(verdicts: Iterable[Verdict[BaseModel]]) -> list[EvaluatorStats]:
    """Latency and cost per evaluator version, sorted by name and version."""
    grouped: dict[tuple[str, str], list[Verdict[BaseModel]]] = {}
    for verdict in verdicts:
        grouped.setdefault((verdict.evaluator, verdict.version), []).append(verdict)
    stats: list[EvaluatorStats] = []
    for (evaluator, version), group in sorted(grouped.items()):
        latencies = sorted(v.latency for v in group)
        costs = [v.cost for v in group if v.cost is not None]
        stats.append(
            EvaluatorStats(
                evaluator=evaluator,
                version=version,
                n=len(group),
                mean_latency=sum(latencies) / len(latencies),
                p50_latency=_nearest_rank(latencies, 0.5),
                p95_latency=_nearest_rank(latencies, 0.95),
                total_cost=sum(costs) if costs else None,
                mean_cost=sum(costs) / len(costs) if costs else None,
            )
        )
    return stats


def _nearest_rank(ordered: Sequence[float], quantile: float) -> float:
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]
