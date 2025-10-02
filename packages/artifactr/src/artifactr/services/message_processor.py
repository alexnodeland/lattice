"""Message processing utilities for agent conversation."""

from datetime import datetime

import tiktoken
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)

from artifactr.db import DatabaseManager
from artifactr.dependencies import get_logger
from artifactr.models.db import Message

logger = get_logger()

# Default token limit for context window
DEFAULT_TOKEN_LIMIT = 4000
# Encoder for tokenizing text
ENCODER = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding


def count_tokens(text: str) -> int:
    """Count the number of tokens in a text string."""
    return len(ENCODER.encode(text))


def get_messages_for_thread(
    db: DatabaseManager,
    thread_id: int,
    token_limit: int = DEFAULT_TOKEN_LIMIT,
    system_prompt: str | None = None,
) -> list[ModelMessage]:
    """Get messages for a thread and convert them to Pydantic AI message format.

    Parameters
    ----------
    db : DatabaseManager
        A database manager instance
    thread_id : int
        ID of the thread to get messages for
    token_limit : int
        Maximum number of tokens to include in the context window
    system_prompt : str | None
        Optional system prompt to use if no system messages are found

    Returns
    -------
    list[ModelMessage]
        A list of ModelMessage objects compatible with Pydantic AI
    """
    # Query all messages for the thread without order (we'll sort them manually)

    thread = db.threads.get_by_id(thread_id)
    if not thread:
        raise ValueError(f"Thread with ID {thread_id} not found")

    # Sort by timestamp
    db_messages = sorted(thread.messages, key=lambda m: m.timestamp)

    if not db_messages:
        # If no messages are found, return just a system prompt if provided
        if system_prompt:
            return [create_system_message(system_prompt)]
        return []

    # Check if we have a system message
    has_system_message = any(msg.type == "system" for msg in db_messages)

    # Initialize with system message if provided and not already present
    pydantic_messages: list[ModelMessage] = []
    if not has_system_message and system_prompt:
        pydantic_messages.append(create_system_message(system_prompt))

    # Track token count
    total_tokens = 0
    if pydantic_messages:
        total_tokens = count_tokens(system_prompt or "")

    # Process messages in chronological order
    processed_messages: list[ModelMessage] = []

    for message in db_messages:
        # Skip system messages if we already added a system prompt
        if message.type == "system" and system_prompt and not processed_messages:
            continue

        pydantic_message = db_message_to_pydantic_message(message)
        if pydantic_message:
            processed_messages.append(pydantic_message)

    # Apply token limit with sliding window
    if token_limit > 0:
        # Start with complete history
        window_messages = processed_messages.copy()

        # Calculate total tokens
        message_tokens = [estimate_message_tokens(msg) for msg in window_messages]
        total_tokens = sum(message_tokens)

        # If we're over the limit, start removing oldest messages until under limit
        # Always keep the most recent user message and response
        while total_tokens > token_limit and len(window_messages) > 2:
            # Remove the oldest message (after any system prompt)
            start_idx = 1 if has_system_message or system_prompt else 0
            removed_message = window_messages.pop(start_idx)
            removed_tokens = estimate_message_tokens(removed_message)
            total_tokens -= removed_tokens

        logger.info(
            f"Created message history with {len(window_messages)} messages ({total_tokens} tokens)"
        )
        return window_messages

    return processed_messages


def db_message_to_pydantic_message(message: Message) -> ModelMessage | None:
    """Convert a database message to a Pydantic AI message."""
    timestamp = message.timestamp or datetime.now()

    if message.type == "system":
        # Create a system message
        return ModelRequest(
            parts=[
                SystemPromptPart(
                    content=message.content,
                    timestamp=timestamp,
                    part_kind="system-prompt",
                )
            ],
            kind="request",
        )
    elif message.type == "user":
        # Create a user message
        return ModelRequest(
            parts=[
                UserPromptPart(
                    content=message.content,
                    timestamp=timestamp,
                    part_kind="user-prompt",
                )
            ],
            kind="request",
        )
    elif message.type in ["response", "idea_agent", "prd_agent"]:
        # Create a model response
        return ModelResponse(
            parts=[
                TextPart(
                    content=message.content,
                    part_kind="text",
                )
            ],
            model_name="gpt-4o",
            timestamp=timestamp,
            kind="response",
        )

    # Skip other message types (e.g., thinking, error, done)
    return None


def create_system_message(system_prompt: str) -> ModelMessage:
    """Create a system message with the given prompt."""
    return ModelRequest(
        parts=[
            SystemPromptPart(
                content=system_prompt,
                timestamp=datetime.now(),
                part_kind="system-prompt",
            )
        ],
        kind="request",
    )


def estimate_message_tokens(message: ModelMessage) -> int:
    """Estimate the number of tokens in a ModelMessage."""
    token_count = 0

    # Count tokens in message parts
    for part in message.parts:
        if hasattr(part, "content"):
            content = getattr(part, "content", "")
            if isinstance(content, str):
                token_count += count_tokens(content)

    # Add overhead for message structure
    token_count += 5

    return token_count
