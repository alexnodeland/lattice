"""Types router for exposing models to OpenAPI schema.

This router exists primarily to ensure that important models like events
and documents are included in the OpenAPI schema generation, making them
available as TypeScript types in the frontend.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from artifactr.models.document import PRD
from artifactr.models.events import (
    AgentActionEvent,
    ClientMessageEvent,
    DocumentEvent,
    DoneEvent,
    ErrorEvent,
    HelloEvent,
    InboundEvent,
    MessageFormatEvent,
    OutboundEvent,
    StopEvent,
    StructuredEvent,
    SystemEvent,
    TaskEvent,
    TokenEvent,
)

router = APIRouter()


class TypesResponse(BaseModel):
    """Response containing type information."""

    message: str
    available_types: list[str]


@router.get("/", response_model=TypesResponse)
async def get_types():
    """Get information about available types.

    This endpoint exists primarily to expose models to the OpenAPI schema.
    """
    return TypesResponse(
        message="Type information endpoint",
        available_types=[
            "PRD",
            "OutboundEvent",
            "InboundEvent",
            "SystemEvent",
            "TokenEvent",
            "TaskEvent",
            "ErrorEvent",
            "MessageFormatEvent",
            "AgentActionEvent",
            "DocumentEvent",
            "StructuredEvent",
            "DoneEvent",
            "HelloEvent",
            "ClientMessageEvent",
            "StopEvent",
        ],
    )


# These endpoints exist solely to include the models in OpenAPI schema
# They return example data and are primarily for type generation


@router.post("/prd/example", response_model=PRD)
async def create_prd_example(prd: PRD):
    """Expose PRD model (for type generation)."""
    return prd


@router.post("/events/outbound/example", response_model=OutboundEvent)
async def create_outbound_event_example(event: OutboundEvent):
    """Expose OutboundEvent model (for type generation)."""
    return event


@router.post("/events/inbound/example", response_model=InboundEvent)
async def create_inbound_event_example(event: InboundEvent):
    """Expose InboundEvent model (for type generation)."""
    return event


@router.post("/events/system/example", response_model=SystemEvent)
async def create_system_event_example(event: SystemEvent):
    """Expose SystemEvent model (for type generation)."""
    return event


@router.post("/events/token/example", response_model=TokenEvent)
async def create_token_event_example(event: TokenEvent):
    """Expose TokenEvent model (for type generation)."""
    return event


@router.post("/events/task/example", response_model=TaskEvent)
async def create_task_event_example(event: TaskEvent):
    """Expose TaskEvent model (for type generation)."""
    return event


@router.post("/events/error/example", response_model=ErrorEvent)
async def create_error_event_example(event: ErrorEvent):
    """Expose ErrorEvent model (for type generation)."""
    return event


@router.post("/events/message-format/example", response_model=MessageFormatEvent)
async def create_message_format_event_example(event: MessageFormatEvent):
    """Expose MessageFormatEvent model (for type generation)."""
    return event


@router.post("/events/agent-action/example", response_model=AgentActionEvent)
async def create_agent_action_event_example(event: AgentActionEvent):
    """Expose AgentActionEvent model (for type generation)."""
    return event


@router.post("/events/document/example", response_model=DocumentEvent)
async def create_document_event_example(event: DocumentEvent):
    """Expose DocumentEvent model (for type generation)."""
    return event


@router.post("/events/structured/example", response_model=StructuredEvent)
async def create_structured_event_example(event: StructuredEvent):
    """Expose StructuredEvent model (for type generation)."""
    return event


@router.post("/events/done/example", response_model=DoneEvent)
async def create_done_event_example(event: DoneEvent):
    """Expose DoneEvent model (for type generation)."""
    return event


@router.post("/events/hello/example", response_model=HelloEvent)
async def create_hello_event_example(event: HelloEvent):
    """Expose HelloEvent model (for type generation)."""
    return event


@router.post("/events/client-message/example", response_model=ClientMessageEvent)
async def create_client_message_event_example(event: ClientMessageEvent):
    """Expose ClientMessageEvent model (for type generation)."""
    return event


@router.post("/events/stop/example", response_model=StopEvent)
async def create_stop_event_example(event: StopEvent):
    """Expose StopEvent model (for type generation)."""
    return event
