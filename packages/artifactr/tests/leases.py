"""A storage some lease holders cannot reach, for the tests of thread claims."""

import asyncio
from collections import Counter
from datetime import timedelta

from artifactr.workspace import InMemoryStorage, Scope


class Partitioned(InMemoryStorage):
    """Storage the lease holders in ``cut_off`` cannot reach, as across a network partition.

    Their lease calls fail at once or, with ``in_flight``, wait until :meth:`heal` and then go
    through, as calls in flight across a partition may.
    """

    def __init__(self, *, in_flight: bool = False) -> None:
        super().__init__()
        self.in_flight = in_flight
        self.cut_off: set[str] = set()
        self.asked = Counter[str]()
        """How many lease calls each holder has made."""
        self.holders: dict[str, str] = {}
        """The holder that last asked for each lease key."""
        self.reached = asyncio.Event()
        """Set once a cut-off holder's lease call has reached the partition."""
        self._healed = asyncio.Event()

    def heal(self) -> None:
        """Let every holder reach the storage again, and calls in flight go through."""
        self.cut_off.clear()
        self._healed.set()

    async def acquire_lease(self, scope: Scope, key: str, holder: str, ttl: timedelta) -> bool:
        self.asked[holder] += 1
        self.holders[key] = holder
        if holder in self.cut_off:
            self.reached.set()
            if not self.in_flight:
                raise ConnectionError("the database is out of reach")
            await self._healed.wait()
        return await super().acquire_lease(scope, key, holder, ttl)
