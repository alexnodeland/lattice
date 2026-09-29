import pytest
from pydantic import ValidationError

from evalr import Verdict

from .models import Helpfulness


def value() -> Helpfulness:
    return Helpfulness(rating=4, resolved=True)


def test_a_verdict_round_trips_as_json() -> None:
    verdict = Verdict(
        value=value(),
        confidence={"rating": 0.9, "resolved": 0.6},
        evaluator="judge",
        version="abc",
        latency=0.25,
        cost=0.001,
        trace_id="0af7651916cd43dd8448eb211c80319c",
    )
    assert Verdict[Helpfulness].model_validate_json(verdict.model_dump_json()) == verdict


def test_defaults() -> None:
    verdict = Verdict(value=value(), evaluator="judge", version="1")
    assert (verdict.confidence, verdict.latency, verdict.cost, verdict.trace_id) == (
        {},
        0.0,
        None,
        None,
    )


def test_verdicts_are_immutable() -> None:
    verdict = Verdict(value=value(), evaluator="judge", version="1")
    name = "evaluator"
    with pytest.raises(ValidationError):
        setattr(verdict, name, "other")


@pytest.mark.parametrize("confidence", [-0.1, 1.5])
def test_confidence_is_a_probability(confidence: float) -> None:
    with pytest.raises(ValidationError):
        Verdict(value=value(), confidence={"rating": confidence}, evaluator="j", version="1")


def test_confidence_is_only_for_the_verdicts_fields() -> None:
    with pytest.raises(ValidationError, match=r"\['mood'\]"):
        Verdict(value=value(), confidence={"mood": 0.5}, evaluator="j", version="1")


@pytest.mark.parametrize("trace_id", ["abc", "0AF7651916CD43DD8448EB211C80319C"])
def test_trace_ids_are_32_lowercase_hex_digits(trace_id: str) -> None:
    with pytest.raises(ValidationError):
        Verdict(value=value(), evaluator="j", version="1", trace_id=trace_id)


@pytest.mark.parametrize(("latency", "cost"), [(-1.0, None), (0.0, -0.01)])
def test_latency_and_cost_are_not_negative(latency: float, cost: float | None) -> None:
    with pytest.raises(ValidationError):
        Verdict(value=value(), evaluator="j", version="1", latency=latency, cost=cost)
