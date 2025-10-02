"""Utilities for streaming events."""

import json
from collections.abc import AsyncGenerator

from artifactr.dependencies import get_logger
from artifactr.models.events import ErrorEvent
from artifactr.services.queue import PrioritizedQueue

logger = get_logger()


async def event_stream(queue: PrioritizedQueue) -> AsyncGenerator[str, None]:
    """
    Consume the prioritized queue and yield events as Server-Sent Events.

    Args
    ----
        queue: PrioritizedQueue containing Event objects

    Yields
    ------
        JSON-serialized Event objects in SSE format (data: <json>)
    """
    try:
        while True:
            evt = await queue.get()
            if evt is None:
                break

            # Format in SSE protocol: "data: <json>\n\n"
            # This is crucial for proper SSE format that clients expect
            yield f"data: {json.dumps(evt.model_dump())}\n\n"

            # Check for DoneEvent to exit the loop
            if hasattr(evt, "type") and evt.type == "done":
                break
    except Exception as e:
        logger.error(f"Error in event_stream: {e!s}")
        # Also format errors in SSE format
        yield f"data: {json.dumps(ErrorEvent(content=f'Stream error: {e!s}').model_dump())}\n\n"
