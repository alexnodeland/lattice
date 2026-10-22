"""A lock PostgreSQL holds for every process that shares its database (ADR-0085).

:class:`AdvisoryLock` takes a transaction-level advisory lock, `pg_advisory_xact_lock`, for each
key, in a transaction of its own on a connection of its own, so runner processes over one
database take turns at a connected app. The transaction's end releases it, whether it commits,
rolls back or its connection is lost, so neither an error, a cancellation nor a process that dies
leaves it held, and nothing is left on a pooled connection. Its wait is bounded by
`lock_timeout`. Each waiter holds a connection while it waits: give it an engine of its own, so
the application's commits never wait for a lock's waiters. Any other database has no such lock:
a single runner process uses the connection's own lock instead.
"""

import hashlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import anyio
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

__all__ = ["AdvisoryLock"]

_LOCK_NOT_AVAILABLE = "55P03"
"""PostgreSQL's SQLSTATE for a lock not taken within `lock_timeout`."""


class AdvisoryLock:
    """A PostgreSQL advisory lock for each key, held across the processes on one database.

    Args:
        engine: PostgreSQL's engine, best one of its own: each waiter holds one of its
            connections.

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
    async def held(self, key: str, *, wait: float) -> AsyncGenerator[None]:
        """Hold the key's lock, waiting for whoever holds it, in any process, at most `wait` s.

        Raises:
            TimeoutError: If it wasn't taken within `wait`.
        """
        number = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], signed=True)
        async with self._engine.connect() as connection:
            try:
                async with connection.begin():
                    milliseconds = max(1, int(wait * 1000))
                    await connection.execute(text(f"SET LOCAL lock_timeout = {milliseconds}"))
                    try:
                        await connection.execute(select(func.pg_advisory_xact_lock(number)))
                    except DBAPIError as error:
                        if getattr(error.orig, "sqlstate", None) == _LOCK_NOT_AVAILABLE:
                            raise TimeoutError(f"the lock wasn't taken within {wait}s") from None
                        raise
                    yield
            except BaseException:
                # Cancelled or failed mid-transaction, the connection may be half-closed: it is
                # thrown away, which ends its session, and so the lock, rather than pooled.
                with anyio.CancelScope(shield=True):
                    await connection.invalidate()
                raise
