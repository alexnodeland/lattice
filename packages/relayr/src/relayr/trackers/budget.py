"""The request budget: how many requests a process makes with each tenant's tracker key a minute.

Plane allows a key 60 requests a minute by default, and one key is one tenant's. Runs' writes
spend the budget first, and are never held back by it; the followers' polls take only what is
left, and wait for their next interval when nothing is. Replicas don't share a budget: one
process polls each binding, by its lease, and the tracker's 429 is the control between them.

A request here is one call of the tracker port, which is one HTTP request for most calls; Plane's
list of a project's items is one per thousand items.
"""

from collections import deque
from datetime import datetime, timedelta
from typing import Final

from relayr.ledger import Clock

WINDOW: Final = timedelta(minutes=1)
"""What the budget is per."""


class Budget:
    """Each tenant's requests in the last minute, in this process.

    Args:
        per_minute: How many requests a minute polls may bring a tenant's spending to.
        clock: Returns the current time, which the minute is measured by.
    """

    def __init__(self, per_minute: int, clock: Clock) -> None:
        self._per_minute = per_minute
        self._clock = clock
        self._spent: dict[str, deque[datetime]] = {}

    def spend(self, tenant: str) -> None:
        """Count a request a run makes: it is made whatever the budget has left."""
        self._recent(tenant).append(self._clock())

    def take(self, tenant: str) -> bool:
        """Count a request a poll makes, if the budget has one left; return whether it had."""
        recent = self._recent(tenant)
        if len(recent) >= self._per_minute:
            return False
        recent.append(self._clock())
        return True

    def _recent(self, tenant: str) -> deque[datetime]:
        recent = self._spent.setdefault(tenant, deque())
        since = self._clock() - WINDOW
        while recent and recent[0] <= since:
            recent.popleft()
        return recent
