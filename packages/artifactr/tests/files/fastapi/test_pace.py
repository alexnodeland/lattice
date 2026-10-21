"""Each person's pace of uploads: a sliding minute, in this process."""

import pytest

from artifactr.files.fastapi.pace import Pace


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_a_person_starts_so_many_in_any_minute() -> None:
    clock = Clock()
    pace = Pace(2, clock=clock)
    assert pace.admit("user:alice") is None
    clock.now += 30
    assert pace.admit("user:alice") is None
    assert pace.admit("user:alice") == 30, "until the first start is a minute old"
    assert pace.admit("user:bob") is None, "each person has their own"
    clock.now += 29.5
    assert pace.admit("user:alice") == 1, "never less than a second"
    clock.now += 0.5
    assert pace.admit("user:alice") is None, "the first start has left the window"
    assert pace.admit("user:alice") == 30


def test_a_pace_lets_one_through_at_least() -> None:
    with pytest.raises(ValueError, match="at least one"):
        Pace(0)
