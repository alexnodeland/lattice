"""Each person's pace of uploads: a sliding minute, in this process."""

import pytest

from artifactr.files.fastapi.pace import KEPT, Gauge, Pace


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_a_person_starts_so_many_in_any_minute() -> None:
    clock = Clock()
    pace = Pace(2, clock=clock)
    assert pace.admit(("acme", "user:alice")) is None
    clock.now += 30
    assert pace.admit(("acme", "user:alice")) is None
    assert pace.admit(("acme", "user:alice")) == 30, "until the first start is a minute old"
    assert pace.admit(("acme", "user:bob")) is None, "each person has their own"
    clock.now += 29.5
    assert pace.admit(("acme", "user:alice")) == 1, "never less than a second"
    clock.now += 0.5
    assert pace.admit(("acme", "user:alice")) is None, "the first start has left the window"
    assert pace.admit(("acme", "user:alice")) == 30


def test_a_pace_lets_one_through_at_least() -> None:
    with pytest.raises(ValueError, match="at least one"):
        Pace(0)


def test_those_who_started_nothing_lately_are_let_go() -> None:
    clock = Clock()
    pace = Pace(1, clock=clock)
    for i in range(KEPT + 1):
        pace.admit(("acme", f"user:{i}"))
    clock.now += 61
    pace.admit(("acme", "user:new"))
    assert pace.admit(("acme", "user:0")) is None
    assert pace.kept == 2


def test_a_gauge_refuses_past_its_most_and_gives_places_back() -> None:
    gauge = Gauge(1)
    with gauge.held() as first, gauge.held() as second:
        assert (first, second) == (True, False)
    with gauge.held() as again:
        assert again
    with pytest.raises(ValueError, match="at least one"):
        Gauge(0)
