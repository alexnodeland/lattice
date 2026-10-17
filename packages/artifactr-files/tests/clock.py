"""A clock that tests move by hand."""

from datetime import UTC, datetime, timedelta

START = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)


class FakeClock:
    """Returns the time it has been moved to, from `START`."""

    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, by: timedelta) -> None:
        self.now += by
