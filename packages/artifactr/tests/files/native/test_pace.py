"""Each person's pace of uploads: a sliding minute, in this process."""

import pytest

from artifactr.files.native.pace import KEPT, Gauge, Pace


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


def test_a_gauge_refuses_past_its_most_or_a_persons_share_and_gives_places_back() -> None:
    gauge = Gauge(2, tenant=2, each=1)
    alice, bob, carol = (("acme", f"user:{n}") for n in ("alice", "bob", "carol"))
    with (
        gauge.held(alice) as first,
        gauge.held(alice) as again,
        gauge.held(bob) as second,
        gauge.held(carol) as third,
    ):
        assert (first, again, second, third) == (True, False, True, False)
    with gauge.held(alice) as after:
        assert after
    shared = Gauge(2, tenant=2, each=2)
    with shared.held(alice), shared.held(alice) as twice:
        assert twice
    with pytest.raises(ValueError, match="at least one"):
        Gauge(1, tenant=1, each=2)


def test_a_gauge_holds_each_tenant_to_its_share() -> None:
    gauge = Gauge(3, tenant=2, each=1)
    with (
        gauge.held(("acme", "user:a")) as a,
        gauge.held(("acme", "user:b")) as b,
        gauge.held(("acme", "user:c")) as c,
        gauge.held(("globex", "user:a")) as g,
    ):
        assert (a, b, c, g) == (True, True, False, True)
