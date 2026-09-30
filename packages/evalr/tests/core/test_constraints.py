"""The constraints evalr's values declare, which coverage cannot see: each value is refused."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from evalr import Example, Score, Verdict

from .models import Helpfulness, Thread


def verdict(**fields: Any) -> Verdict[Helpfulness]:
    return Verdict(value=Helpfulness(rating=4, resolved=True), evaluator="j", version="1", **fields)


@pytest.mark.parametrize(
    "refused",
    [
        lambda: verdict(trace_id="abc"),
        lambda: verdict(trace_id="0AF7651916CD43DD8448EB211C80319C"),
        lambda: verdict(confidence={"rating": -0.1}),
        lambda: verdict(confidence={"rating": 1.5}),
        lambda: verdict(latency=-1.0),
        lambda: verdict(cost=-0.01),
        lambda: setattr(verdict(), "evaluator", "other"),
        lambda: Example[Thread, Helpfulness](id="", input=Thread(messages=[])),
        lambda: Score(
            id="s", name="a.b", value=1.0, data_type="NUMERIC", timestamp=datetime(2026, 9, 29)
        ),
    ],
    ids=[
        "short-trace-id",
        "uppercase-trace-id",
        "negative-confidence",
        "confidence-over-one",
        "negative-latency",
        "negative-cost",
        "frozen-verdict",
        "empty-example-id",
        "naive-score-timestamp",
    ],
)
def test_a_value_refuses_what_it_declares_it_cannot_hold(refused: Callable[[], object]) -> None:
    with pytest.raises(ValidationError):
        refused()
