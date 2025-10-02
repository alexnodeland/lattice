from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import Agent

from artifactr.db import DatabaseManager
from artifactr.models.document import PRD
from artifactr.models.events import DoneEvent, ErrorEvent, SystemEvent
from artifactr.services.agent import (
    ThreadLabel,
    agent_conversation,
    build_conversational_agent,
    build_idea_agent,
    build_prd_agent,
    build_thread_labeler_agent,
)
from artifactr.services.queue import PrioritizedQueue


@pytest.fixture
def mock_queue():
    """Create a mock queue for testing."""
    return MagicMock(spec=PrioritizedQueue)


@pytest.fixture
def thread(session):
    """Create a test thread in the database."""
    db = DatabaseManager(session)
    thread = db.threads.create(title="Test Thread", description="Test Description")
    return thread


@pytest.fixture
def mock_idea_agent():
    """Create a mock idea agent for testing."""
    agent = MagicMock(spec=Agent)

    # Create a proper async context manager mock
    mock_stream = AsyncMock()
    mock_stream.__aenter__ = AsyncMock()
    mock_stream.__aexit__ = AsyncMock()

    async def mock_stream_text():
        yield "test"
        yield " response"

    mock_stream.__aenter__.return_value.stream_text = mock_stream_text
    agent.run_stream.return_value = mock_stream

    return agent


@pytest.mark.asyncio
async def test_build_idea_agent():
    """Test building an idea agent."""
    with (
        patch("backend.services.agent.MCPServerHTTP") as mock_mcp,
        patch("backend.services.agent.Agent") as mock_agent_class,
    ):
        # Setup
        mock_agent_instance = MagicMock()
        mock_agent_class.return_value = mock_agent_instance
        mock_mcp_instance = MagicMock()
        mock_mcp.return_value = mock_mcp_instance

        # Execute
        agent = build_idea_agent("localhost", 8000)

        # Verify
        mock_mcp.assert_called_once_with(url="http://localhost:8000/sse")
        mock_agent_class.assert_called_once()
        args, kwargs = mock_agent_class.call_args
        assert kwargs["model"] == "openai:gpt-4o"
        assert "Idea agent" in kwargs["system_prompt"]
        assert mock_mcp_instance in kwargs["mcp_servers"]
        assert agent == mock_agent_instance


@pytest.mark.asyncio
async def test_build_prd_agent():
    """Test building a PRD agent."""
    with patch("backend.services.agent.Agent") as mock_agent_class:
        # Setup
        mock_agent_instance = MagicMock()
        mock_agent_class.return_value = mock_agent_instance

        # Execute
        agent = build_prd_agent()

        # Verify
        mock_agent_class.assert_called_once()
        args, kwargs = mock_agent_class.call_args
        assert kwargs["model"] == "openai:gpt-4o"
        assert kwargs["output_type"] == PRD
        assert agent == mock_agent_instance


@pytest.mark.asyncio
async def test_build_conversational_agent():
    """Test building a conversational agent."""
    with patch("backend.services.agent.Agent") as mock_agent_class:
        # Setup
        mock_agent_instance = MagicMock()
        mock_agent_class.return_value = mock_agent_instance

        # Execute
        agent = build_conversational_agent()

        # Verify
        mock_agent_class.assert_called_once()
        args, kwargs = mock_agent_class.call_args
        assert kwargs["model"] == "openai:gpt-4o"
        assert "helpful assistant" in kwargs["system_prompt"]
        assert agent == mock_agent_instance


@pytest.mark.asyncio
async def test_build_thread_labeler_agent():
    """Test building a thread labeler agent."""
    with patch("backend.services.agent.Agent") as mock_agent_class:
        # Setup
        mock_agent_instance = MagicMock()
        mock_agent_class.return_value = mock_agent_instance

        # Execute
        agent = build_thread_labeler_agent()

        # Verify
        mock_agent_class.assert_called_once()
        args, kwargs = mock_agent_class.call_args
        assert kwargs["model"] == "openai:gpt-4-mini"
        assert "expert summarizer" in kwargs["system_prompt"]
        assert kwargs["output_type"] == ThreadLabel
        assert agent == mock_agent_instance


@pytest.mark.asyncio
async def test_agent_conversation_existing_thread(
    mock_queue, session, thread, mock_idea_agent
):
    """Test agent conversation with an existing thread."""
    db = DatabaseManager(session)

    # Mock agents and streams
    with (
        patch("backend.services.agent.build_conversational_agent") as mock_build_conv,
        patch("backend.services.agent.get_messages_for_thread") as mock_get_messages,
        patch("backend.services.agent.MessageFormatContext") as mock_context,
        patch("backend.services.agent.build_prd_agent") as mock_build_prd,
    ):
        mock_agent = MagicMock()
        mock_build_conv.return_value = mock_agent
        mock_get_messages.return_value = []

        # Mock MessageFormatContext
        mock_context.return_value.__aenter__ = AsyncMock()
        mock_context.return_value.__aexit__ = AsyncMock()

        # Mock PRD agent
        mock_prd_agent = MagicMock()
        mock_build_prd.return_value = mock_prd_agent

        # Mock the stream - create a proper async context manager
        mock_stream_result = AsyncMock()

        async def mock_stream_text():
            yield "Hello"
            yield " world"

        mock_stream_result.stream_text = mock_stream_text

        # Create an async context manager that returns the mock_stream_result
        mock_stream_context = AsyncMock()
        mock_stream_context.__aenter__ = AsyncMock(return_value=mock_stream_result)
        mock_stream_context.__aexit__ = AsyncMock(return_value=None)

        mock_agent.run_stream.return_value = mock_stream_context
        mock_agent.tool = MagicMock(return_value=lambda x: x)  # Mock decorator

        # Execute
        await agent_conversation(
            queue=mock_queue,
            message="Hello",
            idea_agent=mock_idea_agent,
            db=db,
            thread_id=thread.id,
        )

        # Verify
        mock_build_conv.assert_called_once()
        # Since there's no message history (empty list), it should call without message_history
        mock_agent.run_stream.assert_called_once_with("Hello")

        # Verify events were sent to the queue
        system_calls = [
            call
            for call in mock_queue.put.call_args_list
            if isinstance(call[0][0], SystemEvent)
            and call[0][0].content == "Processing message: Hello"
        ]
        assert len(system_calls) > 0

        done_calls = [
            call
            for call in mock_queue.put.call_args_list
            if isinstance(call[0][0], DoneEvent)
        ]
        assert len(done_calls) > 0


@pytest.mark.asyncio
async def test_agent_conversation_new_thread(mock_queue, session, mock_idea_agent):
    """Test agent conversation with a new thread (no thread ID)."""
    db = DatabaseManager(session)

    # Mock agents
    with (
        patch("backend.services.agent.build_conversational_agent") as mock_build_conv,
        patch(
            "backend.services.agent.build_thread_labeler_agent"
        ) as mock_build_labeler,
        patch("backend.services.agent.get_messages_for_thread") as mock_get_messages,
        patch("backend.services.agent.MessageFormatContext") as mock_context,
        patch("backend.services.agent.build_prd_agent") as mock_build_prd,
    ):
        # Mock conversational agent
        mock_conv_agent = MagicMock()
        mock_build_conv.return_value = mock_conv_agent
        mock_get_messages.return_value = []

        # Mock MessageFormatContext
        mock_context.return_value.__aenter__ = AsyncMock()
        mock_context.return_value.__aexit__ = AsyncMock()

        # Mock PRD agent
        mock_prd_agent = MagicMock()
        mock_build_prd.return_value = mock_prd_agent

        # Mock the stream - create a proper async context manager
        mock_stream_result = AsyncMock()

        async def mock_stream_text():
            yield "Hello"
            yield " world"

        mock_stream_result.stream_text = mock_stream_text

        # Create an async context manager that returns the mock_stream_result
        mock_stream_context = AsyncMock()
        mock_stream_context.__aenter__ = AsyncMock(return_value=mock_stream_result)
        mock_stream_context.__aexit__ = AsyncMock(return_value=None)

        mock_conv_agent.run_stream.return_value = mock_stream_context
        mock_conv_agent.tool = MagicMock(return_value=lambda x: x)  # Mock decorator

        # Mock thread labeler
        mock_labeler_agent = MagicMock()
        mock_build_labeler.return_value = mock_labeler_agent

        # Mock thread label result
        mock_thread_label = MagicMock()
        mock_thread_label.output = MagicMock()
        mock_thread_label.output.title = "New Title"
        mock_thread_label.output.description = "New Description"
        mock_labeler_agent.run.return_value = mock_thread_label

        # Count threads before the function call
        thread_count_before = len(db.threads.get_all())

        # Execute
        await agent_conversation(
            queue=mock_queue,
            message="Hello",
            idea_agent=mock_idea_agent,
            db=db,
            thread_id=None,
        )

        # Verify a thread was created
        thread_count_after = len(db.threads.get_all())
        assert thread_count_after > thread_count_before

        # Verify
        mock_build_conv.assert_called_once()
        mock_conv_agent.run_stream.assert_called_once_with("Hello")

        mock_build_labeler.assert_called_once()
        mock_labeler_agent.run.assert_called_once()

        # Verify events were sent to the queue using content matching
        system_calls = [
            call
            for call in mock_queue.put.call_args_list
            if isinstance(call[0][0], SystemEvent)
            and call[0][0].content == "Processing message: Hello"
        ]
        assert len(system_calls) > 0

        done_calls = [
            call
            for call in mock_queue.put.call_args_list
            if isinstance(call[0][0], DoneEvent)
        ]
        assert len(done_calls) > 0


@pytest.mark.asyncio
async def test_agent_conversation_error_handling(mock_queue, session, mock_idea_agent):
    """Test error handling in agent conversation."""
    db = DatabaseManager(session)

    # Setup - simulate thread lookup failure by mocking the threads repository
    with (
        patch.object(db.threads, "get_by_id", side_effect=ValueError("Test error")),
        patch("backend.services.agent.get_messages_for_thread") as mock_get_messages,
    ):
        mock_get_messages.return_value = []

        # Execute
        await agent_conversation(
            queue=mock_queue,
            message="Hello",
            idea_agent=mock_idea_agent,
            db=db,
            thread_id=999,
        )

        # Verify events were sent to the queue - check content not exact instances
        system_calls = [
            call
            for call in mock_queue.put.call_args_list
            if isinstance(call[0][0], SystemEvent)
            and call[0][0].content == "Processing message: Hello"
        ]
        assert len(system_calls) > 0

        # Error should be sent to the queue
        error_calls = [
            call
            for call in mock_queue.put.call_args_list
            if isinstance(call[0][0], ErrorEvent)
        ]
        assert len(error_calls) > 0

        # Done event should still be sent
        done_calls = [
            call
            for call in mock_queue.put.call_args_list
            if isinstance(call[0][0], DoneEvent)
        ]
        assert len(done_calls) > 0
