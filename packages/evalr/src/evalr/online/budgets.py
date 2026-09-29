"""Budgets: how much online evaluation may spend in a period."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

__all__ = ["Budget"]


def _now() -> datetime:
    return datetime.now(UTC)


class Budget:
    """At most a number of evaluations, a cost in US dollars, or both, per period.

    The budget is checked before each evaluation, and spent after it, so the evaluation that
    crosses a limit completes: it is a soft limit. A new period starts from nothing.
    """

    def __init__(
        self,
        *,
        max_evaluations: int | None = None,
        max_cost: float | None = None,
        period: timedelta = timedelta(days=1),
        clock: Callable[[], datetime] = _now,
    ) -> None:
        """Set the limits.

        Args:
            max_evaluations: Evaluations allowed per period.
            max_cost: US dollars allowed per period, counting the verdicts that report a cost.
            period: How long a period lasts, from the first check.
            clock: The time; the system's by default.

        Raises:
            ValueError: A limit is negative, or the period is not positive.
        """
        if (max_evaluations is not None and max_evaluations < 0) or (
            max_cost is not None and max_cost < 0
        ):
            raise ValueError("budget limits cannot be negative")
        if period <= timedelta(0):
            raise ValueError("a budget's period must be positive")
        self.max_evaluations = max_evaluations
        self.max_cost = max_cost
        self.period = period
        self.clock = clock
        self._started: datetime | None = None
        self.evaluations = 0
        self.cost = 0.0

    def allows(self) -> bool:
        """Whether another evaluation fits in this period."""
        now = self.clock()
        if self._started is None or now - self._started >= self.period:
            self._started, self.evaluations, self.cost = now, 0, 0.0
        within_count = self.max_evaluations is None or self.evaluations < self.max_evaluations
        within_cost = self.max_cost is None or self.cost < self.max_cost
        return within_count and within_cost

    def spend(self, cost: float | None) -> None:
        """Count an evaluation, and its cost when known."""
        self.evaluations += 1
        self.cost += cost or 0.0
