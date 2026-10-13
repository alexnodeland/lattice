"""Awaiting a database call to its end, and locking a row to change it.

A caller can be cancelled at any await: by a timeout, a stopped worker or a closed connection.
A database call cancelled halfway can leave a connection, a lock or a transaction behind, so
storage awaits each call to its end, and raises the cancellation after it.
"""

import asyncio
import contextlib
import functools
from collections.abc import Awaitable, Callable
from types import CoroutineType
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["awaited_to_the_end", "lock_row", "to_the_end"]


async def to_the_end[T](call: Awaitable[T]) -> T:
    """Await a database call to its end; a cancellation that came meanwhile is raised after."""
    task = asyncio.ensure_future(call)
    cancelled: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.wait([task])
        except asyncio.CancelledError as error:
            cancelled = error
    if cancelled is not None:
        if not task.cancelled():
            task.exception()
        raise cancelled
    return task.result()


def awaited_to_the_end[**P, T](
    method: Callable[P, Awaitable[T]],
) -> Callable[P, "CoroutineType[Any, Any, T]"]:  # subscriptable at run time from Python 3.13
    """Await every call of a method to its end, with :func:`to_the_end`."""

    @functools.wraps(method)
    async def call(*args: P.args, **kwargs: P.kwargs) -> T:
        return await to_the_end(method(*args, **kwargs))

    return call


async def lock_row[R](session: AsyncSession, model: type[R], key: object, new: R) -> R:
    """Lock a row (``SELECT ... FOR UPDATE``), inserting ``new`` first if it does not exist.

    ``key`` is the row's primary key, as SQLAlchemy's ``AsyncSession.get`` takes it: a value, a
    tuple or a mapping.
    """
    while (row := await session.get(model, key, with_for_update=True)) is None:
        # A concurrent transaction may insert the row first. Then this insert fails, and the
        # next lookup waits for that transaction to end and locks its row instead.
        with contextlib.suppress(IntegrityError):
            async with session.begin_nested():
                session.add(new)
    return row
