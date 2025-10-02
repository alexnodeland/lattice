"""Agents for the backend."""

import json
import time

from pydantic import BaseModel, Field, ValidationError
from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import MCPServerHTTP

from artifactr.db import DatabaseManager
from artifactr.dependencies import get_logger
from artifactr.models.document import PRD
from artifactr.models.events import (
    DocumentEvent,
    DoneEvent,
    ErrorEvent,
    MessageFormatContext,
    StructuredEvent,
    SystemEvent,
    TokenEvent,
)
from artifactr.services.message_processor import get_messages_for_thread
from artifactr.services.queue import PrioritizedQueue

logger = get_logger()


def build_idea_agent(mcp_host: str, mcp_port: int) -> Agent:
    """Build an agent that can call the Idea MCP server."""
    mcp_url = f"http://{mcp_host}:{mcp_port}/sse"
    mcp_http = MCPServerHTTP(url=mcp_url)
    return Agent(
        model="openai:gpt-4o",
        system_prompt=(
            "You are an Idea agent. You can interact with an Idea."
            "You can:"
            "   - Get an Idea by ID"
            "   - List all Ideas"
            "   - Create a new Idea"
            "   - Update an existing Idea"
            "   - Delete an existing Idea"
            "Call the appropriate tool based on the user's request."
        ),
        mcp_servers=[mcp_http],
    )


def build_prd_agent() -> Agent[None, PRD]:
    """Build a PRD agent."""
    return Agent(
        model="openai:gpt-4o",
        system_prompt=(
            "You are an expert PRD writer.",
            "You can:"
            "   - Get a PRD by ID."
            "   - List all PRDs."
            "   - Create a new PRD."
            "   - Update existing PRDs."
            "   - Delete existing PRDs."
            "Call the appropriate tool based on the user's request.",
        ),
        output_type=PRD,
    )


def build_conversational_agent() -> Agent[None, str]:
    """Build a conversational agent."""
    return Agent(
        model="openai:gpt-4o",
        system_prompt=(
            "You are a helpful assistant with access to a team of specialized assistants. "
            "Always delegate to the appropriate specialized model when applicable"
            "Be friendly, helpful, and leverage your team's expertise in your responses."
        ),
    )


class ThreadLabel(BaseModel):
    """A label for a thread."""

    title: str = Field(
        ...,
        description="A short description of the thread.",
    )
    description: str = Field(
        ...,
        description="A longer description of the thread (1-2 sentences).",
    )


def build_thread_labeler_agent() -> Agent[None, ThreadLabel]:
    """Build an agent that can label a thread."""
    return Agent(
        model="openai:gpt-4-mini",
        system_prompt=(
            "You are an expert summarizer."
            "You digest large amounts of text and distill it into a short title and description."
            "The title should be a single phrase that captures the essence of the thread."
            "The description should be a short summary of the thread."
        ),
        output_type=ThreadLabel,
    )


async def agent_conversation(
    queue: PrioritizedQueue,
    message: str,
    idea_agent: Agent | None,
    db: DatabaseManager,
    thread_id: int | None = None,
):
    """Stream responses from a conversational agent that can orchestrate other agents that can call MCP servers.

    Parameters
    ----------
    queue : PrioritizedQueue
        AsyncIO queue for publishing events
    message : str
        The user's message
    idea_agent : Agent | None
        The idea agent
    db : DatabaseManager
        The database manager
    thread_id : int | None
        Identifier for the chat thread (integer ID)
    """
    # Store thread ID to avoid session.refresh issues
    current_thread_id = None

    try:
        # Log the start of the conversation
        system_event = SystemEvent(content=f"Processing message: {message}")
        await queue.put(system_event)

        # Get the thread
        if thread_id:
            thread = db.threads.get_by_id(thread_id)
            if not thread:
                raise ValueError(f"Thread with ID {thread_id} not found")
            # Store thread ID as local variable to avoid session bound issues
            current_thread_id = thread.id
        else:
            thread = db.threads.create(title="New Thread", description="New Thread")
            current_thread_id = thread.id

        # Store user message in database
        db.messages.create(
            thread_id=current_thread_id, type="user", content=message, meta={}
        )

        # Get thread message history in Pydantic AI format with token limit
        message_history = []
        if current_thread_id:
            # Default system prompt if needed
            system_prompt = (
                "You are a helpful assistant with access to a team of specialized assistants. "
                "Always delegate to the appropriate specialized model when applicable. "
                "Be friendly, helpful, and leverage your team's expertise in your responses."
            )
            message_history = get_messages_for_thread(
                db, current_thread_id, system_prompt=system_prompt
            )
            logger.info(
                f"Retrieved {len(message_history)} messages from thread history"
            )

        conversational_agent = build_conversational_agent()

        @conversational_agent.tool()
        async def call_idea_agent(ctx: RunContext[None], message: str) -> str:
            """Call the idea agent to interact with an Idea.

            Idea agent capabilities:
                - Get an Idea by ID
                - List all Ideas
                - Create a new Idea
                - Update an existing Idea
                - Delete an existing Idea

            Parameters
            ----------
            message : str
                The message to send to the idea agent

            Returns
            -------
            str
                The response from the idea agent
            """
            # Stream tokens to the queue while collecting the full output
            output = ""
            db.messages.create(
                thread_id=current_thread_id,
                type="thinking",
                content=f"Calling idea agent with message: {message}",
                meta={},
            )

            async with MessageFormatContext(
                queue, f"Calling idea agent with message: {message}", "thinking"
            ) as _:
                if idea_agent is None:
                    raise ValueError("Idea agent is not initialized")
                async with idea_agent.run_stream(message) as result:
                    async for token in result.stream_text():
                        output += token
                        await queue.put(TokenEvent(content=token))

            # Store the full response for message history (tokens are for streaming only)
            # This is saved directly since there's no IdeaAgentResponseEvent type
            db.messages.create(
                thread_id=current_thread_id, type="idea_agent", content=output, meta={}
            )
            return output

        prd_agent = build_prd_agent()

        @conversational_agent.tool()
        async def call_prd_agent(ctx: RunContext[None], message: str) -> PRD:
            """
            Call the PRD agent to write a PRD.

            PRD agent capabilities:
                - Get a PRD by ID
                - List all PRDs
                - Create a new PRD
                - Update existing PRDs
                - Delete existing PRDs

            Parameters
            ----------
                message: The message to send to the PRD agent

            Returns
            -------
                The response from the PRD agent
            """
            output = None
            db.messages.create(
                thread_id=current_thread_id,
                type="thinking",
                content=f"Calling PRD agent with message: {message}",
                meta={},
            )

            async with prd_agent.run_stream(message) as result:
                async for m, last in result.stream_structured(debounce_by=0.01):
                    try:
                        # Validate the structured output
                        structured_data = await result.validate_structured_output(
                            m, allow_partial=not last
                        )
                        # Send the validated data
                        await queue.put(
                            StructuredEvent(
                                data_type="document.prd",
                                data=structured_data,
                                is_partial=not last,
                            )
                        )
                        # Capture the final output when we reach the last chunk
                        if last:
                            # Store the structured data as a PRD
                            output = structured_data
                    except ValidationError:
                        if last:
                            raise ValidationError(
                                "PRD agent failed to generated valid output"
                            )
                        # Skip invalid intermediate states
                        continue

            if output is None:
                raise ValueError("No output from PRD agent")

            # Store the PRD response for message history
            # This is saved directly since structured events are for streaming only
            db.messages.create(
                thread_id=current_thread_id,
                type="prd_agent",
                content=json.dumps(output.model_dump()),
                meta={"document_type": "prd"},
            )

            # Send document event through queue (will be saved via send_event)
            await queue.put(
                DocumentEvent(
                    content="Completed PRD",
                    document_id=str(time.time_ns()),
                    document_type="prd",
                    document_data=output,
                )
            )
            return output

        # Run the conversational agent
        response_content = ""

        # Use the message history if we have it
        if message_history:
            logger.info(
                f"Running agent with message history ({len(message_history)} messages)"
            )
            async with conversational_agent.run_stream(
                message, message_history=message_history
            ) as result:
                async for token in result.stream_text():
                    response_content += token
                    await queue.put(TokenEvent(content=token))
        else:
            # First message, no history
            logger.info("Running agent without message history (first message)")
            async with conversational_agent.run_stream(message) as result:
                async for token in result.stream_text():
                    response_content += token
                    await queue.put(TokenEvent(content=token))

        # Store the full response for message history (tokens are for streaming only)
        # This is saved directly since there's no ResponseEvent type
        db.messages.create(
            thread_id=current_thread_id,
            type="response",
            content=response_content,
            meta={},
        )

        # Label the thread if it's new
        # Get a fresh thread object from the database
        if current_thread_id is not None:
            thread_to_update = db.threads.get_by_id(current_thread_id)
            if (
                thread_to_update
                and thread_to_update.title == "New Thread"
                and thread_to_update.description == "New Thread"
            ):
                thread_labeler_agent = build_thread_labeler_agent()
                result = await thread_labeler_agent.run(thread_to_update.description)
                # Update the thread using the repository method
                db.threads.update(
                    thread_to_update,
                    {
                        "title": result.output.title,
                        "description": result.output.description,
                    },
                )
    except Exception as e:
        error_event = ErrorEvent(content=str(e))
        await queue.put(error_event)

        # Store error in the database
        try:
            db.messages.create(
                thread_id=current_thread_id,
                type="error",
                content=str(e),
                meta=error_event.metadata,
            )
        except Exception as error_ex:
            logger.error(f"Failed to store error message: {error_ex}")
    finally:
        done_event = DoneEvent()
        await queue.put(done_event)

        # Store done event in the database
        try:
            if current_thread_id is not None:
                db.messages.create(
                    thread_id=current_thread_id,
                    type="done",
                    content="",
                    meta=done_event.metadata,
                )
        except Exception as done_ex:
            logger.error(f"Failed to store done message: {done_ex}")

        logger.info(f"[{thread_id}] Agent run terminated")
