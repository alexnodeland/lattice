"""
Event models for the streaming API.

This module defines the event types used in the streaming API, using a
discriminated union pattern for type safety.
"""

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from artifactr.models.document import PRD


#
# Outbound Events
#
class BaseEvent(BaseModel):
    """Base class for all event types."""

    timestamp: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SystemEvent(BaseEvent):
    """System-level messages about the overall process."""

    type: Literal["system"] = "system"
    content: str


class TokenEvent(BaseEvent):
    """Individual tokens received from the LLM."""

    type: Literal["token"] = "token"
    content: str


class TaskEvent(BaseEvent):
    """Updates from concurrent background tasks."""

    type: Literal["task"] = "task"
    content: str


class ErrorEvent(BaseEvent):
    """Error messages when something goes wrong."""

    type: Literal["error"] = "error"
    content: str


message_format_types = Literal["thinking", "agent_action"]


class MessageFormatEvent(BaseEvent):
    """Formatting instructions for UI rendering with opening/closing tags support."""

    type: Literal["message_format"] = "message_format"
    content: str
    format: message_format_types
    is_opening: bool = True  # True for opening tag, False for closing tag
    identifier: str = Field(
        default_factory=lambda: str(time.time_ns())
    )  # Unique identifier to pair opens/closes


class MessageFormatContext:
    """
    Context manager for message formatting.

    This context manager handles the opening and closing of message format events
    to ensure they are always properly paired.

    Examples
    --------
    >>> async with MessageFormatContextManager(queue, "Thinking about this...", "thinking") as mgr:
    ...     # Do something while the thinking format is active
    ...     await queue.put(TokenEvent(content="Some token"))
    """

    def __init__(
        self,
        queue,
        content: str,
        format_type: message_format_types,
        identifier: str | None = None,
    ):
        """
        Initialize the context manager.

        Parameters
        ----------
        queue : PrioritizedQueue
            The queue to put the message format events on.
        content : str
            The content of the message format event.
        format_type : Literal["thinking", "agent_action"]
            The type of format to use.
        identifier : str | None
            A unique identifier to pair opening and closing events.
            If not provided, a timestamp-based ID will be generated.
        """
        self.queue = queue
        self.content = content
        # Explicitly store as the correct type
        if format_type == "thinking":
            self.format_type: message_format_types = "thinking"
        elif format_type == "agent_action":
            self.format_type: message_format_types = "agent_action"
        else:
            raise ValueError(f"Invalid format type: {format_type}")
        self.identifier = identifier if identifier is not None else str(time.time_ns())

    async def __aenter__(self):
        """Open the message format."""
        await self.queue.put(
            MessageFormatEvent(
                content=self.content,
                format=self.format_type,
                is_opening=True,
                identifier=self.identifier,
            )
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close the message format."""
        await self.queue.put(
            MessageFormatEvent(
                content="",
                format=self.format_type,
                is_opening=False,
                identifier=self.identifier,
            )
        )
        return False  # Don't suppress exceptions


class AgentActionEvent(BaseEvent):
    """Tool usage by the agent."""

    type: Literal["agent_action"] = "agent_action"
    content: str
    tool: str
    inputs: dict[str, Any]


class DocumentEvent(BaseEvent):
    """Document content updates."""

    type: Literal["document"] = "document"
    content: str
    document_id: str
    document_type: Literal["generic", "prd"] = "generic"
    document_data: dict | PRD | None = None


class StructuredEvent(BaseEvent):
    """Structured data events for streaming typed objects."""

    type: Literal["structured"] = "structured"
    data_type: Literal["generic", "document.generic", "document.prd"]
    data: Any
    is_partial: bool = True


class DoneEvent(BaseEvent):
    """Done event to indicate the end of the stream."""

    type: Literal["done"] = "done"


# Discriminated Union of All Outbound Events
OutboundEvent = (
    SystemEvent
    | TokenEvent
    | TaskEvent
    | ErrorEvent
    | MessageFormatEvent
    | AgentActionEvent
    | DocumentEvent
    | StructuredEvent
    | DoneEvent
)


#
# Inbound Events
#
class HelloEvent(BaseEvent):
    """Hello event to identify the connection."""

    type: Literal["hello"] = "hello"
    protocol_version: str


class ClientMessageEvent(BaseEvent):
    """Client message event to send a message to the server."""

    type: Literal["message"] = "message"
    content: str


class StopEvent(BaseEvent):
    """Stop event to stop the server."""

    type: Literal["stop"] = "stop"
    reason: str | None = None


# Discriminated Union of All Inbound Events
InboundEvent = HelloEvent | ClientMessageEvent | StopEvent

# Discriminated Union of All Events
Event = InboundEvent | OutboundEvent
