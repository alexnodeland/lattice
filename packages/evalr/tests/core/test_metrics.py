"""Metrics, property-tested against reference implementations (scikit-learn, SciPy, NumPy)."""

from typing import Annotated, Any, Literal

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel, Field
from scipy.stats import spearmanr
from sklearn.metrics import accuracy_score, brier_score_loss, cohen_kappa_score
from sklearn.metrics import mean_absolute_error as sk_mean_absolute_error

from evalr import Verdict
from evalr.core import (
    FieldKind,
    accuracy,
    agreement,
    agreement_score,
    brier_score,
    calibration,
    cohen_kappa,
    evaluator_stats,
    expected_calibration_error,
    field_agreement,
    mean_absolute_error,
    spearman,
)

# ─── strategies ───────────────────────────────────────────────────────────────


def pairs[T](
    values: st.SearchStrategy[T], min_size: int = 0
) -> st.SearchStrategy[tuple[list[T], list[T]]]:
    return st.integers(min_size, 40).flatmap(
        lambda n: st.tuples(
            st.lists(values, min_size=n, max_size=n), st.lists(values, min_size=n, max_size=n)
        )
    )


labels = st.integers(0, 3)
numbers = st.one_of(
    st.integers(-5, 5).map(float),
    st.floats(-1e3, 1e3, allow_nan=False, allow_infinity=False),
)
probabilities = st.floats(0.0, 1.0, allow_nan=False)
calibrated = st.integers(0, 40).flatmap(
    lambda n: st.tuples(
        st.lists(probabilities, min_size=n, max_size=n),
        st.lists(st.booleans(), min_size=n, max_size=n),
    )
)

# ─── against the references ───────────────────────────────────────────────────


@given(pairs(labels, min_size=1))
def test_accuracy_matches_scikit_learn(data: tuple[list[int], list[int]]) -> None:
    expected, predicted = data
    assert accuracy(expected, predicted) == pytest.approx(accuracy_score(expected, predicted))


@given(pairs(labels, min_size=1))
def test_kappa_matches_scikit_learn(data: tuple[list[int], list[int]]) -> None:
    expected, predicted = data
    kappa = cohen_kappa(expected, predicted)
    if kappa is None:
        assert len(set(expected) | set(predicted)) == 1
    else:
        assert kappa == pytest.approx(cohen_kappa_score(expected, predicted), abs=1e-9)


@given(pairs(numbers, min_size=1))
def test_mean_absolute_error_matches_scikit_learn(data: tuple[list[float], list[float]]) -> None:
    expected, predicted = data
    assert mean_absolute_error(expected, predicted) == pytest.approx(
        sk_mean_absolute_error(expected, predicted), rel=1e-9, abs=1e-9
    )


def scipy_spearman(expected: list[float], predicted: list[float]) -> float:
    result: Any = spearmanr(expected, predicted)
    return float(result.statistic)


@given(pairs(numbers, min_size=2))
def test_spearman_matches_scipy(data: tuple[list[float], list[float]]) -> None:
    expected, predicted = data
    rho = spearman(expected, predicted)
    if rho is None:
        assert len(set(expected)) == 1 or len(set(predicted)) == 1
    else:
        assert rho == pytest.approx(scipy_spearman(expected, predicted), abs=1e-9)


@given(calibrated.filter(lambda d: len(d[0]) > 0))
def test_brier_score_matches_scikit_learn(data: tuple[list[float], list[bool]]) -> None:
    confidences, correct = data
    assert brier_score(confidences, correct) == pytest.approx(
        brier_score_loss(correct, confidences, pos_label=True), abs=1e-12
    )


def reference_ece(confidences: list[float], correct: list[bool], bins: int) -> float:
    c = np.asarray(confidences, dtype=float)
    ok = np.asarray(correct, dtype=float)
    which = np.minimum((c * bins).astype(int), bins - 1)
    return float(
        sum(
            np.mean(which == b) * abs(np.mean(ok[which == b]) - np.mean(c[which == b]))
            for b in range(bins)
            if np.any(which == b)
        )
    )


@given(calibrated.filter(lambda d: len(d[0]) > 0), st.integers(1, 20))
def test_calibration_error_matches_a_numpy_reference(
    data: tuple[list[float], list[bool]], bins: int
) -> None:
    confidences, correct = data
    ece = expected_calibration_error(confidences, correct, bins=bins)
    assert ece == pytest.approx(reference_ece(confidences, correct, bins), abs=1e-9)
    assert ece is not None
    assert 0.0 <= ece <= 1.0


@given(calibrated.filter(lambda d: len(d[0]) > 0))
def test_one_bin_compares_mean_confidence_with_accuracy(
    data: tuple[list[float], list[bool]],
) -> None:
    confidences, correct = data
    gap = abs(sum(correct) / len(correct) - sum(confidences) / len(confidences))
    assert expected_calibration_error(confidences, correct, bins=1) == pytest.approx(gap, abs=1e-9)


# ─── edges ────────────────────────────────────────────────────────────────────


def test_empty_inputs_are_undefined() -> None:
    assert accuracy([], []) is None
    assert cohen_kappa([], []) is None
    assert mean_absolute_error([], []) is None
    assert spearman([], []) is None
    assert brier_score([], []) is None
    assert expected_calibration_error([], []) is None


def test_undefined_correlations() -> None:
    assert spearman([1.0], [2.0]) is None
    assert spearman([1.0, 1.0], [1.0, 2.0]) is None
    assert cohen_kappa(["a", "a"], ["a", "a"]) is None
    assert cohen_kappa(["a"], ["b"]) == 0.0
    assert spearman([1.0, 2.0], [2.0, 1.0]) == -1.0


def test_lengths_must_match() -> None:
    with pytest.raises(ValueError, match="2 expected values but 1 predicted"):
        accuracy([1, 2], [1])


def test_confidences_are_probabilities() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        brier_score([1.5], [True])


def test_bins_are_positive() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        expected_calibration_error([0.5], [True], bins=0)


# ─── verdicts ─────────────────────────────────────────────────────────────────


class Review(BaseModel):
    rating: Annotated[int, Field(ge=1, le=5)]
    resolved: bool
    tone: Literal["warm", "cold"] | None = None
    delay: float | None = None
    reason: str | None = None


def review(rating: int, resolved: bool, **kw: object) -> Review:
    return Review.model_validate({"rating": rating, "resolved": resolved, **kw})


def test_field_agreement_by_kind() -> None:
    expected = review(5, True, tone="warm", delay=2.0, reason="x")
    predicted = review(4, False, tone=None, delay=1.0, reason="y")
    assert field_agreement(expected, predicted) == {
        "rating": 0.75,
        "resolved": 0.0,
        "tone": 0.0,
        "delay": 0.5,
    }
    assert agreement_score(expected, predicted) == pytest.approx(1.25 / 4)
    assert agreement_score(expected, expected) == 1.0


def test_fields_without_an_expected_value_do_not_count() -> None:
    assert field_agreement(review(3, True), review(3, True, tone="cold")) == {
        "rating": 1.0,
        "resolved": 1.0,
    }


def test_a_missing_verdict_agrees_not_at_all() -> None:
    assert agreement_score(review(3, True), None) == 0.0


def test_a_verdict_with_nothing_compared_has_no_score() -> None:
    class Note(BaseModel):
        text: str | None = None

    assert agreement_score(Note(), Note(text="x")) is None


def test_agreement_over_verdicts() -> None:
    expected = [review(5, True, tone="warm"), review(1, False), review(3, True, delay=1.0)]
    predicted = [review(5, True, tone="cold"), review(2, False), None]
    result = agreement(expected, predicted, verdict_type=Review)
    assert result.n == 3
    assert list(result.fields) == ["rating", "resolved", "tone", "delay"]
    rating = result.fields["rating"]
    assert (rating.kind, rating.n, rating.missing) == (FieldKind.ORDINAL, 3, 1)
    assert rating.mean_absolute_error == 0.5
    assert rating.spearman == pytest.approx(1.0)
    assert rating.score == pytest.approx((1.0 + 0.75 + 0.0) / 3)
    assert (rating.accuracy, rating.kappa) == (None, None)
    resolved = result.fields["resolved"]
    assert resolved.accuracy == pytest.approx(2 / 3)
    assert resolved.kappa == pytest.approx(cohen_kappa_score(["1", "0", "1"], ["1", "0", "None"]))
    assert (resolved.mean_absolute_error, resolved.spearman) == (None, None)
    tone = result.fields["tone"]
    assert (tone.n, tone.accuracy, tone.kappa) == (1, 0.0, 0.0)
    delay = result.fields["delay"]
    assert (delay.n, delay.missing, delay.mean_absolute_error, delay.score) == (1, 1, None, 0.0)
    assert result.score == pytest.approx(((1.0 + 1.0 + 0.0) / 3 + (0.75 + 1.0) / 2 + 0.0) / 3)


def test_agreement_over_nothing() -> None:
    result = agreement([], [], verdict_type=Review)
    assert (result.n, result.score) == (0, None)
    assert result.fields["rating"].score is None


def verdict(value: Review, confidence: dict[str, float], **kw: object) -> Verdict[Review]:
    return Verdict.model_validate(
        {"value": value, "confidence": confidence, "evaluator": "e", "version": "1", **kw}
    )


def test_calibration_per_field() -> None:
    expected = [review(5, True), review(1, False, tone="warm"), review(3, True)]
    verdicts = [
        verdict(review(5, True), {"rating": 0.9, "resolved": 0.8}),
        verdict(review(2, False, tone="cold"), {"rating": 0.6, "tone": 0.7}),
        None,
    ]
    result = calibration(expected, verdicts, verdict_type=Review, bins=5)
    assert list(result) == ["rating", "resolved", "tone"]
    rating = result["rating"]
    assert (rating.n, rating.accuracy, rating.confidence) == (2, 0.5, pytest.approx(0.75))
    assert rating.brier_score == pytest.approx(((0.9 - 1) ** 2 + 0.6**2) / 2)
    assert rating.expected_calibration_error == pytest.approx((0.1 + 0.6) / 2)
    assert (result["tone"].n, result["tone"].accuracy) == (1, 0.0)


def test_confidence_for_an_unlabelled_field_is_skipped() -> None:
    result = calibration(
        [review(3, True)], [verdict(review(3, True), {"tone": 0.9})], verdict_type=Review
    )
    assert result == {}


def test_evaluator_stats() -> None:
    verdicts = [
        verdict(review(1, True), {}, latency=float(i), cost=0.01 if i % 2 else None)
        for i in range(1, 21)
    ] + [verdict(review(1, True), {}, evaluator="a", version="2", latency=1.0)]
    first, second = evaluator_stats(verdicts)
    assert (first.evaluator, first.version, first.n) == ("a", "2", 1)
    assert (first.total_cost, first.mean_cost) == (None, None)
    assert (second.evaluator, second.n, second.mean_latency) == ("e", 20, 10.5)
    assert (second.p50_latency, second.p95_latency) == (10.0, 19.0)
    assert second.total_cost == pytest.approx(0.1)
    assert second.mean_cost == pytest.approx(0.01)
