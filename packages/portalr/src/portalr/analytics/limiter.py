"""How fast a person may send events: a port, so a shared limiter can replace this process's own.

The relay asks one :class:`RateLimiter`. :class:`InMemoryRateLimiter` counts in the process, so
each replica counts apart: with three replicas a person may send three times the rate. A limiter
over Valkey, which the stack runs under its ``langfuse`` and ``gateway`` profiles but not under
``analytics`` alone, can take its place without the relay changing (lattice RFC-0008).
"""

import time
from collections.abc import Callable
from typing import Protocol


class RateLimiter(Protocol):
    """Says whether a key may spend `cost` now, and if not, how long until it may."""

    def spend(self, key: str, cost: int) -> float | None:
        """None if allowed, and spent; otherwise the seconds until `cost` is available."""
        ...


class InMemoryRateLimiter:
    """A token bucket per key, in this process: `burst` at most, refilled at `per_second`.

    Args:
        per_second: How many tokens a key gains each second.
        burst: How many it may hold, and so spend at once.
        most_keys: How many keys it remembers; past it, the fullest are forgotten first.
        clock: Seconds, rising; ``time.monotonic`` unless a test says otherwise.
    """

    def __init__(
        self,
        per_second: float = 1.0,
        burst: int = 60,
        *,
        most_keys: int = 100_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._rate = per_second
        self._burst = burst
        self._most = most_keys
        self._clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}

    def spend(self, key: str, cost: int) -> float | None:
        """None if the key had `cost` tokens, now spent; else the seconds until it will."""
        now = self._clock()
        tokens, then = self._buckets.get(key, (float(self._burst), now))
        tokens = min(float(self._burst), tokens + (now - then) * self._rate)
        if cost > tokens:
            self._buckets[key] = (tokens, now)
            return (cost - tokens) / self._rate
        self._buckets[key] = (tokens - cost, now)
        if len(self._buckets) > self._most:
            # A key at its burst is no different from one never seen: forgetting it costs nothing.
            fullest = max(self._buckets, key=lambda k: self._buckets[k][0])
            del self._buckets[fullest]
        return None
