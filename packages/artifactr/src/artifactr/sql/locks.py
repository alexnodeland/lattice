"""A lock PostgreSQL holds for every process that shares its database (ADR-0085).

:class:`AdvisoryLock` takes a session-level advisory lock, `pg_advisory_lock`, for each key, on a
connection of its own for as long as it is held, so runner processes over one database take turns
at a connected app. Ending the connection releases it, so a process that dies holds nothing. Any
other database has no such lock: a single runner process uses the connection's own lock instead.
"""

import hashlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

__all__ = ["AdvisoryLock"]


class AdvisoryLock:
    """A PostgreSQL advisory lock for each key, held across the processes on one database.

    Raises:
        ValueError: If the engine isn't PostgreSQL's.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        if engine.dialect.name != "postgresql":
            raise ValueError(
                f"{engine.dialect.name} has no advisory locks: one runner process uses the"
                " connection's own lock"
            )
        self._engine = engine

    @asynccontextmanager
    async def held(self, key: str) -> AsyncGenerator[None]:
        """Hold the key's lock, waiting for whoever holds it, in any process."""
        number = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], signed=True)
        async with self._engine.connect() as connection:
            await connection.execute(select(func.pg_advisory_lock(number)))
            try:
                yield
            finally:
                await connection.execute(select(func.pg_advisory_unlock(number)))
