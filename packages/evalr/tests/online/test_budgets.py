from datetime import UTC, datetime, timedelta

import pytest

from evalr.online import Budget


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 28, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def test_a_count_budget() -> None:
    budget = Budget(max_evaluations=2)
    assert budget.allows()
    budget.spend(None)
    assert budget.allows()
    budget.spend(None)
    assert not budget.allows()


def test_a_cost_budget_is_soft() -> None:
    budget = Budget(max_cost=0.01)
    assert budget.allows()
    budget.spend(0.02)
    assert not budget.allows()
    assert (budget.evaluations, budget.cost) == (1, 0.02)


def test_a_new_period_starts_from_nothing() -> None:
    clock = Clock()
    budget = Budget(max_evaluations=1, period=timedelta(hours=1), clock=clock)
    assert budget.allows()
    budget.spend(0.5)
    assert not budget.allows()
    clock.now += timedelta(minutes=59)
    assert not budget.allows()
    clock.now += timedelta(minutes=1)
    assert budget.allows()
    assert (budget.evaluations, budget.cost) == (0, 0.0)


def test_no_limits_allow_everything() -> None:
    budget = Budget()
    for _ in range(100):
        budget.spend(1.0)
    assert budget.allows()


def test_limits_are_checked() -> None:
    with pytest.raises(ValueError, match="negative"):
        Budget(max_evaluations=-1)
    with pytest.raises(ValueError, match="negative"):
        Budget(max_cost=-0.5)
    with pytest.raises(ValueError, match="positive"):
        Budget(period=timedelta(0))
