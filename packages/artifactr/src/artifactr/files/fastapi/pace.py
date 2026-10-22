"""How many uploads each person may start in a minute, and this process takes at once."""

import math
import time
from collections import Counter, defaultdict, deque
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Final

MINUTE: Final = 60.0
KEPT: Final = 4096
"""How many people's windows are kept before those that have emptied are let go."""


class Pace:
    """At most `per_minute` starts by each of a tenant's people in any sixty seconds.

    A sliding window, this process's own, so each replica of an application keeps its own.
    """

    def __init__(self, per_minute: int, *, clock: Callable[[], float] = time.monotonic) -> None:
        if per_minute < 1:
            raise ValueError("a pace lets at least one upload a minute through")
        self._most = per_minute
        self._clock = clock
        self._started: defaultdict[tuple[str, str], deque[float]] = defaultdict(deque)

    def admit(self, who: tuple[str, str]) -> int | None:
        """Count a start by a tenant's participant; or, past the pace, the seconds to wait."""
        now = self._clock()
        if len(self._started) > KEPT:
            self._let_go(now)
        started = self._started[who]
        while started and started[0] <= now - MINUTE:
            started.popleft()
        if len(started) >= self._most:
            return max(1, math.ceil(started[0] + MINUTE - now))
        started.append(now)
        return None

    @property
    def kept(self) -> int:
        """How many people's windows are kept."""
        return len(self._started)

    def _let_go(self, now: float) -> None:
        """Forget everyone who started nothing in the last minute."""
        for who in [w for w, s in self._started.items() if not s or s[-1] <= now - MINUTE]:
            del self._started[who]


class Gauge:
    """At most `most` at once, `tenant` of them a tenant's, and `each` of them a person's.

    Past any of them, another is refused, never queued.
    """

    def __init__(self, most: int, *, tenant: int, each: int) -> None:
        if not 1 <= each <= tenant <= most:
            raise ValueError(
                "a gauge lets each person at least one place, no more than their tenant, and a "
                f"tenant no more than all: not {each} each, {tenant} a tenant, {most} in all"
            )
        self._most = most
        self._tenant = tenant
        self._each = each
        self._held: Counter[tuple[str, str]] = Counter()

    @contextmanager
    def held(self, who: tuple[str, str]) -> Generator[bool]:
        """Hold a place for a tenant's participant while the block runs, yielding True.

        Yields False instead if no place is free, or their tenant or they hold their share.
        """
        tenants = sum(n for (tenant, _), n in self._held.items() if tenant == who[0])
        if (
            self._held.total() >= self._most
            or tenants >= self._tenant
            or self._held[who] >= self._each
        ):
            yield False
            return
        self._held[who] += 1
        try:
            yield True
        finally:
            self._held[who] -= 1
            if not self._held[who]:
                del self._held[who]
