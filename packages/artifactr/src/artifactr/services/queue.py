"""Queue service."""

import asyncio

from artifactr.dependencies import settings
from artifactr.models.events import (
    DoneEvent,
    ErrorEvent,
    OutboundEvent,
    SystemEvent,
)


class PrioritizedQueue:
    """Prioritized queue for outbound events."""

    def __init__(self, maxsize: int):
        self.hp: asyncio.Queue[OutboundEvent] = asyncio.Queue()
        self.lp: asyncio.Queue[OutboundEvent] = asyncio.Queue(maxsize=maxsize)
        self.timeout = settings.put_timeout

    async def put(self, event: OutboundEvent):
        """Put an event into the queue.

        Parameters
        ----------
        event : OutboundEvent
            The event to put into the queue
        """
        if isinstance(event, SystemEvent | ErrorEvent | DoneEvent):
            await self.hp.put(event)
        else:
            try:
                await asyncio.wait_for(self.lp.put(event), self.timeout)
            except (TimeoutError, asyncio.QueueFull):
                try:
                    self.lp.get_nowait()
                except Exception:
                    pass
                try:
                    self.lp.put_nowait(event)
                except Exception:
                    pass

    async def get(self) -> OutboundEvent:
        """Get an event from the queue."""
        if not self.hp.empty():
            return await self.hp.get()
        return await self.lp.get()

    def empty(self) -> bool:
        """Check if the queue is empty."""
        return self.hp.empty() and self.lp.empty()
