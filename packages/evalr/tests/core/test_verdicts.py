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


def test_confidence_is_only_for_the_verdicts_fields() -> None:
    with pytest.raises(ValidationError, match=r"\['mood'\]"):
        Verdict(value=value(), confidence={"mood": 0.5}, evaluator="j", version="1")
