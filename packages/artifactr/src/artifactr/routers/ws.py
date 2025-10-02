"""WebSocket router."""

import asyncio
import json
import random
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError
from pydantic.type_adapter import TypeAdapter
from pydantic_ai import Agent

from artifactr.db import DatabaseManager
from artifactr.dependencies import get_db, get_logger, settings
from artifactr.models.db import Message
from artifactr.models.events import (
    DoneEvent,
    ErrorEvent,
    HelloEvent,
    InboundEvent,
    OutboundEvent,
    SystemEvent,
)
from artifactr.services.agent import agent_conversation
from artifactr.services.queue import PrioritizedQueue

logger = get_logger()
router = APIRouter()


# In-memory store for current session (temporary until retrieved from db)
history_store: dict[int, list[OutboundEvent]] = defaultdict(list)


def convert_db_message_to_event(message: Message) -> OutboundEvent:
    """Convert a database Message to an OutboundEvent."""
    event_type = message.type
    timestamp = (
        message.timestamp.timestamp()
        if message.timestamp
        else datetime.now().timestamp()
    )
    # Ensure metadata is a proper dict with string keys
    metadata_dict: dict[str, Any] = {}
    if message.meta:
        metadata_dict = (
            {str(k): v for k, v in message.meta.items()}
            if isinstance(message.meta, dict)
            else {}
        )

    if event_type == "system":
        return SystemEvent(
            content=message.content, metadata=metadata_dict, timestamp=timestamp
        )
    elif event_type == "error":
        return ErrorEvent(
            content=message.content, metadata=metadata_dict, timestamp=timestamp
        )
    elif event_type == "done":
        return DoneEvent(metadata=metadata_dict, timestamp=timestamp)
    else:
        # For other message types, create a generic OutboundEvent
        return OutboundEvent.__call__(  # type: ignore
            type=event_type,
            content=message.content,
            metadata=metadata_dict,
            timestamp=timestamp,
        )


class ConversationSession:
    """Conversation session."""

    def __init__(
        self,
        ws: WebSocket,
        idea_agent: Agent | None,
        db: DatabaseManager,
        thread_id: int,
        since: float | None,
    ):
        self.ws = ws
        self.agent = idea_agent
        self.db = db
        self.thread_id = thread_id
        self.since = since
        self.queue = PrioritizedQueue(settings.queue_maxsize)
        self.agent_task: asyncio.Task | None = None
        self.drain_task: asyncio.Task | None = None
        self.heartbeat_task: asyncio.Task | None = None

    async def accept_and_validate(self) -> bool:
        """Accept and validate the WebSocket connection."""
        await self.ws.accept()
        logger.info(f"[{self.thread_id}] WS connection accepted")

        raw = await self.ws.receive_text()
        try:
            hello = HelloEvent.model_validate_json(raw)
        except ValidationError:
            await self.send_event(ErrorEvent(content="Expected hello event"))
            await self.ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return False

        if hello.protocol_version != settings.protocol_version:
            await self.send_event(
                ErrorEvent(content=f"Unsupported protocol {hello.protocol_version}")
            )
            await self.ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return False

        await self.send_event(
            SystemEvent(content=f"Protocol negotiated: {settings.protocol_version}")
        )

        # Check if the thread exists, create it if it doesn't
        try:
            thread = self.db.threads.get_by_id(self.thread_id)
            if not thread:
                logger.info(f"[{self.thread_id}] Thread not found, creating a new one")
                try:
                    thread = self.db.threads.create(
                        title=f"Auto-created Thread {self.thread_id}",
                        description="This thread was automatically created by the system",
                    )
                    await self.send_event(
                        SystemEvent(content=f"Created new thread with ID: {thread.id}")
                    )
                except Exception as e:
                    # If database operation fails, just log it and continue
                    logger.warning(
                        f"[{self.thread_id}] Failed to save thread to database: {e}"
                    )
                    await self.send_event(
                        SystemEvent(
                            content=f"Using ephemeral thread with ID: {self.thread_id}"
                        )
                    )

            # Load message history from database
            try:
                # Clear any previously cached messages for this thread
                history_store[self.thread_id].clear()

                # Query messages for this thread ordered by timestamp
                thread = self.db.threads.get_by_id(self.thread_id)
                if not thread:
                    raise ValueError("Thread not found")
                messages = thread.time_ordered_messages

                # Convert database messages to events and add to history
                for message in messages:
                    event = convert_db_message_to_event(message)
                    history_store[self.thread_id].append(event)

                logger.info(
                    f"[{self.thread_id}] Loaded {len(messages)} messages from database"
                )
            except Exception as e:
                logger.warning(
                    f"[{self.thread_id}] Failed to load message history: {e}"
                )

        except Exception as e:
            # If any database operation fails, just log it and continue
            logger.warning(f"[{self.thread_id}] Database error: {e}")
            await self.send_event(
                SystemEvent(content=f"Using ephemeral thread with ID: {self.thread_id}")
            )

        # Send previous messages that are newer than the since timestamp
        if self.since is not None:
            messages_sent = 0
            for event in history_store[self.thread_id]:
                if event.timestamp > self.since:
                    await self.send_event(
                        event, save_to_db=False
                    )  # Don't re-save to DB
                    messages_sent += 1

            logger.info(
                f"[{self.thread_id}] Sent {messages_sent} historical messages (since {self.since})"
            )

        self.heartbeat_task = asyncio.create_task(self._heartbeat())
        return True

    async def start_new_turn(self, message: str):
        """Start a new turn."""
        logger.info(f"[{self.thread_id}] Starting new turn: {message!r}")
        await self._cancel_current()
        self.agent_task = asyncio.create_task(
            agent_conversation(
                queue=self.queue,
                message=message,
                thread_id=self.thread_id,
                idea_agent=self.agent,
                db=self.db,
            )
        )
        self.drain_task = asyncio.create_task(self._drain_queue())

    async def stop(self, reason: str = "Stopped by user"):
        """Stop the conversation."""
        logger.info(f"[{self.thread_id}] Stop requested")
        await self._cancel_current()
        await self.send_event(SystemEvent(content=reason))

    async def _cancel_current(self):
        """Cancel the current task."""
        for t in (self.agent_task, self.drain_task):
            if t and not t.done():
                t.cancel()
        self.agent_task = self.drain_task = None

    async def _drain_queue(self):
        """Drain the queue."""
        try:
            while True:
                event = await self.queue.get()
                await self.send_event(event)
                if isinstance(event, DoneEvent):
                    break
        except asyncio.CancelledError:
            logger.debug(f"[{self.thread_id}] Drain cancelled")
        except Exception as exc:
            await self.send_event(ErrorEvent(content=str(exc)))

    async def send_event(self, event: OutboundEvent, save_to_db: bool = True):
        """Send an event to the WebSocket connection."""
        # Save event to history store
        history_store[self.thread_id].append(event)

        # Define streaming-only event types that should not be persisted to DB
        # These are for real-time display only and excluded from message history
        streaming_only_types = {
            "token",
            "message_format",
            "thinking",
            "agent_action",
        }

        # Save to database if we have a valid thread_id and save_to_db is True
        # Skip streaming-only events (tokens are for real-time display only)
        if save_to_db and event.type not in streaming_only_types:
            try:
                if self.thread_id:
                    # Get content if the event has it
                    message_content = ""
                    if hasattr(event, "content"):
                        message_content = getattr(event, "content", "")

                    # Ensure metadata is a plain dict
                    event_metadata = {}
                    if hasattr(event, "metadata") and event.metadata is not None:
                        # Convert all keys to strings to ensure compatibility
                        event_metadata = {str(k): v for k, v in event.metadata.items()}

                    message = Message(
                        thread_id=self.thread_id,
                        type=event.type,
                        content=message_content,
                        timestamp=datetime.fromtimestamp(event.timestamp),
                        meta=event_metadata,
                    )
                    self.db.session.add(message)
                    self.db.session.commit()
            except Exception as e:
                logger.warning(
                    f"[{self.thread_id}] Failed to save message to database: {e}"
                )

        # Send event to client
        await self.ws.send_text(event.model_dump_json())

    async def _heartbeat(self):
        """Heartbeat the WebSocket connection."""
        try:
            while True:
                await asyncio.sleep(settings.heartbeat_interval)
                try:
                    await asyncio.wait_for(
                        self.ws.receive_text(), settings.ws_receive_timeout
                    )
                except TimeoutError:
                    logger.warning(f"[{self.thread_id}] Heartbeat timed out; closing")
                    await self.ws.close(code=status.WS_1001_GOING_AWAY)
                    break
        except asyncio.CancelledError:
            pass


class ConnectionManager:
    """Connection manager."""

    def __init__(self):
        self._sessions: dict[int, list[ConversationSession]] = defaultdict(list)

    async def connect(self, conv: ConversationSession):
        """Connect a conversation session."""
        self._sessions[conv.thread_id].append(conv)

    async def disconnect(self, conv: ConversationSession):
        """Disconnect a conversation session."""
        sessions = self._sessions.get(conv.thread_id, [])
        if conv in sessions:
            sessions.remove(conv)
        await conv._cancel_current()

    async def broadcast_room(self, thread_id: int, event: OutboundEvent):
        """Broadcast an event to a specific thread."""
        for conv in self._sessions.get(thread_id, []):
            await conv.send_event(event)

    async def broadcast_all(self, event: OutboundEvent):
        """Broadcast an event to all sessions."""
        for sessions in self._sessions.values():
            for conv in sessions:
                await conv.send_event(event)

    def count_active(self) -> int:
        """Count the number of active sessions."""
        return sum(len(s) for s in self._sessions.values())

    def count_per_room(self) -> dict[int, int]:
        """Count the number of sessions per thread."""
        return {room: len(sessions) for room, sessions in self._sessions.items()}


manager = ConnectionManager()


@router.websocket("/ws/{thread_id}")
async def ws_agent_chat(
    websocket: WebSocket,
    thread_id: int,
    db: DatabaseManager = Depends(get_db),
):
    """WebSocket router for agent chat."""
    since = None
    try:
        since_param = websocket.query_params.get("since") or None
        if since_param is not None:
            since = float(since_param)
    except ValueError:
        pass  # since remains None

    # Get the idea agent
    idea_agent = None
    # Try to get the app state from the websocket scope
    if websocket.scope and "app" in websocket.scope:
        app = websocket.scope.get("app")
        if app is not None and hasattr(app, "state"):
            idea_agent = getattr(app.state, "idea_agent", None)

    # In production, we must have an idea_agent
    if idea_agent is None and settings.mode == "production":
        logger.error("Idea agent not found in app state and running in production mode")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    conv = ConversationSession(
        ws=websocket,
        idea_agent=idea_agent,
        db=db,
        thread_id=thread_id,
        since=since,
    )
    if not await conv.accept_and_validate():
        return

    await manager.connect(conv)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                inbound = TypeAdapter(InboundEvent).validate_python(data)
            except (json.JSONDecodeError, ValidationError) as e:
                logger.error(f"[{thread_id}] Invalid inbound: {e}")
                await conv.send_event(ErrorEvent(content="Invalid message format"))
                continue

            if inbound.type == "message":
                await conv.start_new_turn(inbound.content)
            elif inbound.type == "stop":
                await conv.stop(inbound.reason or "Stopped by user")
            else:
                await conv.send_event(
                    ErrorEvent(content=f"Unsupported event: {inbound.type!r}")
                )
    except WebSocketDisconnect:
        logger.info(f"[{thread_id}] WS disconnected")
    finally:
        await manager.disconnect(conv)


@router.websocket("/ws")
async def ws_agent_chat_new_thread(
    websocket: WebSocket,
    db: DatabaseManager = Depends(get_db),
):
    """WebSocket router for agent chat with automatic thread creation."""
    # Create a new thread
    try:
        try:
            # Verify the session is working by attempting a simple operation
            # This will fail if there's no database binding
            thread = db.threads.create(
                title="New Conversation",
                description="Automatically created conversation thread",
            )
            thread_id = thread.id

            if thread_id is None:
                raise ValueError("Thread ID is None after commit")

        except Exception as e:
            # Database error - create a mock thread instead
            logger.warning(f"Database error when creating thread: {e}")
            # Use a random thread ID
            thread_id = random.randint(1, 10000)
            logger.info(f"Created mock thread with ID: {thread_id}")

    except Exception as e:
        logger.error(f"Failed to create thread: {e}")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    logger.info(f"Created new thread with ID: {thread_id}")

    # Redirect to the regular WebSocket handler with the new thread ID
    since = None

    # Get the idea agent
    idea_agent = None
    # Try to get the app state from the websocket scope
    if websocket.scope and "app" in websocket.scope:
        app = websocket.scope.get("app")
        if app is not None and hasattr(app, "state"):
            idea_agent = getattr(app.state, "idea_agent", None)

    # In production, we must have an idea_agent
    if idea_agent is None and settings.mode == "production":
        logger.error("Idea agent not found in app state and running in production mode")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    # Create a modified conversation session that doesn't re-accept the connection
    class ThreadCreatedSession(ConversationSession):
        async def accept_and_validate(self) -> bool:
            """Validate the WebSocket connection but don't re-accept it."""
            # Skip the websocket.accept() call since we'll do it outside
            logger.info(f"[{self.thread_id}] WS connection already accepted")

            raw = await self.ws.receive_text()
            try:
                hello = HelloEvent.model_validate_json(raw)
            except ValidationError:
                await self.send_event(ErrorEvent(content="Expected hello event"))
                await self.ws.close(code=status.WS_1008_POLICY_VIOLATION)
                return False

            if hello.protocol_version != settings.protocol_version:
                await self.send_event(
                    ErrorEvent(content=f"Unsupported protocol {hello.protocol_version}")
                )
                await self.ws.close(code=status.WS_1008_POLICY_VIOLATION)
                return False

            await self.send_event(
                SystemEvent(content=f"Protocol negotiated: {settings.protocol_version}")
            )

            # Thread is already created, no need to check
            if self.since is not None:
                for event in history_store[self.thread_id]:
                    if event.timestamp > self.since:
                        await self.send_event(event)

            self.heartbeat_task = asyncio.create_task(self._heartbeat())
            return True

    conv = ThreadCreatedSession(
        ws=websocket,
        idea_agent=idea_agent,
        db=db,
        thread_id=thread_id,
        since=since,
    )

    # Accept the WebSocket connection
    await websocket.accept()

    # Send initial message with the thread ID
    init_message = json.dumps({"thread_id": thread_id, "type": "thread_created"})
    await websocket.send_text(init_message)

    if not await conv.accept_and_validate():
        return

    await manager.connect(conv)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                inbound = TypeAdapter(InboundEvent).validate_python(data)
            except (json.JSONDecodeError, ValidationError) as e:
                logger.error(f"[{thread_id}] Invalid inbound: {e}")
                await conv.send_event(ErrorEvent(content="Invalid message format"))
                continue

            if inbound.type == "message":
                await conv.start_new_turn(inbound.content)
            elif inbound.type == "stop":
                await conv.stop(inbound.reason or "Stopped by user")
            else:
                await conv.send_event(
                    ErrorEvent(content=f"Unsupported event: {inbound.type!r}")
                )
    except WebSocketDisconnect:
        logger.info(f"[{thread_id}] WS disconnected")
    finally:
        await manager.disconnect(conv)
