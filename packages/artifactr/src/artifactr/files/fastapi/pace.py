"""How many uploads each person may start in a minute, in this process."""

import math
import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Final

MINUTE: Final = 60.0


class Pace:
    """At most `per_minute` starts by each participant in any sixty seconds: a sliding window.

    It is this process's count, so each replica of an application keeps its own.
    """

    def __init__(self, per_minute: int, *, clock: Callable[[], float] = time.monotonic) -> None:
        if per_minute < 1:
            raise ValueError("a pace lets at least one upload a minute through")
        self._most = per_minute
        self._clock = clock
        self._started: defaultdict[str, deque[float]] = defaultdict(deque)

    def admit(self, participant: str) -> int | None:
        """Count a start, and return None; or, past the pace, the whole seconds to wait."""
        now = self._clock()
        started = self._started[participant]
        while started and started[0] <= now - MINUTE:
            started.popleft()
        if len(started) >= self._most:
            return max(1, math.ceil(started[0] + MINUTE - now))
        started.append(now)
        return None
