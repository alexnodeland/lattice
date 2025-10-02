"""Stream router for handling streaming event endpoints."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import artifactr.error_code as codes
from artifactr.db import DatabaseManager
from artifactr.dependencies import get_db, settings
from artifactr.services.agent import agent_conversation
from artifactr.services.queue import PrioritizedQueue
from artifactr.utils import event_stream

router = APIRouter()


class AgentChatRequest(BaseModel):
    """Request body for agent chat streaming endpoint."""

    message: str = Field(..., description="User message to process")


@router.post("/{thread_id}")
async def stream_agent_chat(
    _request: Request,
    thread_id: int,
    request: AgentChatRequest,
    db: DatabaseManager = Depends(get_db),
):
    """
    Invoke an agent conversation with the given thread ID.

    Parameters
    ----------
    thread_id: int
        Identifier for the chat thread
    request: AgentChatRequest
        The request body containing the user message

    Returns
    -------
    StreamingResponse
        An NDJSON-style streaming response
    """
    queue = PrioritizedQueue(settings.queue_maxsize)

    # Check if thread exists
    thread = db.threads.get_by_id(thread_id)
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=codes.THREAD_DOES_NOT_EXIST,
        )

    # Get the idea agent from application state
    idea_agent = None
    if hasattr(_request.app.state, "idea_agent"):
        idea_agent = _request.app.state.idea_agent
    else:
        # This should only happen if the app is not properly initialized
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent service is not available",
        )

    # Fire off the agent stream without blocking
    asyncio.create_task(  # noqa: RUF006
        agent_conversation(
            queue=queue,
            message=request.message,
            thread_id=thread_id,
            idea_agent=idea_agent,
            db=db,
        )
    )

    # Return an SSE-formatted streaming response
    return StreamingResponse(
        event_stream(queue),
        media_type="text/event-stream",  # Correct MIME type for SSE
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
