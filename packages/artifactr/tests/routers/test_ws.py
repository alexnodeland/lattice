import json

import pytest
from fastapi.testclient import TestClient

from artifactr.models.events import DoneEvent, HelloEvent, SystemEvent


def test_ws_connection(client: TestClient, thread):
    """Test WebSocket connection establishment and protocol negotiation."""
    thread_id = thread.id
    with client.websocket_connect(f"/ws/{thread_id}") as websocket:
        # Send hello event
        hello = HelloEvent(protocol_version="1.0")
        websocket.send_text(hello.model_dump_json())

        # Receive response - should be a system event
        response = json.loads(websocket.receive_text())
        assert response["type"] == "system"
        assert "Protocol negotiated" in response["content"]


def test_ws_invalid_protocol(client: TestClient, thread):
    """Test rejection of invalid protocol version."""
    thread_id = thread.id
    with client.websocket_connect(f"/ws/{thread_id}") as websocket:
        # Send hello with invalid protocol
        hello = HelloEvent(protocol_version="999.0")
        websocket.send_text(hello.model_dump_json())

        # Should receive error and close
        response = json.loads(websocket.receive_text())
        assert response["type"] == "error"
        assert "Unsupported protocol" in response["content"]

        # Connection should close with policy violation
        with pytest.raises(Exception):
            websocket.receive_text()


def test_ws_thread_not_found(client: TestClient):
    """Test connection to non-existent thread, which now creates a new thread."""
    with client.websocket_connect("/ws/999999") as websocket:
        # Send valid hello
        hello = HelloEvent(protocol_version="1.0")
        websocket.send_text(hello.model_dump_json())

        # Should get system message first
        response = json.loads(websocket.receive_text())
        assert response["type"] == "system"

        # Should get a system message about creating a new thread
        response = json.loads(websocket.receive_text())
        assert response["type"] == "system"
        assert "Created new thread" in response["content"]


def test_ws_message_processing(client: TestClient, thread, monkeypatch):
    """Test sending a message and receiving appropriate responses."""
    thread_id = thread.id

    # Mock agent_conversation to avoid actual processing
    async def mock_agent_conv(*args, **kwargs):
        queue = kwargs.get("queue")
        if queue:
            # Create proper event instances for each message type
            system1 = SystemEvent(content="Thinking...")
            system2 = SystemEvent(content="Response message")
            done = DoneEvent()

            # Add events to queue
            await queue.put(system1)
            await queue.put(system2)
            await queue.put(done)

    monkeypatch.setattr("backend.routers.ws.agent_conversation", mock_agent_conv)

    with client.websocket_connect(f"/ws/{thread_id}") as websocket:
        # Send hello event
        hello = HelloEvent(protocol_version="1.0")
        websocket.send_text(hello.model_dump_json())

        # Skip system message
        websocket.receive_text()

        # Send a message - construct the JSON directly to avoid using InboundEvent
        websocket.send_text(json.dumps({"type": "message", "content": "Hello agent"}))

        # Should receive thinking, message, and done events
        response1 = json.loads(websocket.receive_text())
        assert response1["type"] == "system"
        assert response1["content"] == "Thinking..."

        response2 = json.loads(websocket.receive_text())
        assert response2["type"] == "system"
        assert response2["content"] == "Response message"

        response3 = json.loads(websocket.receive_text())
        assert response3["type"] == "done"


def test_ws_stop_conversation(client: TestClient, thread, monkeypatch):
    """Test stopping an ongoing conversation."""
    thread_id = thread.id

    # Setup a long-running mock
    async def mock_agent_conv(*args, **kwargs):
        # This will be cancelled before it completes
        queue = kwargs.get("queue")
        if queue:
            system1 = SystemEvent(content="Thinking...")
            system2 = SystemEvent(content="Part 1")

            # Add events to queue
            await queue.put(system1)
            await queue.put(system2)
            # Would send more but will be cancelled

    monkeypatch.setattr("backend.routers.ws.agent_conversation", mock_agent_conv)

    with client.websocket_connect(f"/ws/{thread_id}") as websocket:
        # Send hello
        hello = HelloEvent(protocol_version="1.0")
        websocket.send_text(hello.model_dump_json())
        websocket.receive_text()  # Skip system message

        # Start conversation - construct the JSON directly
        websocket.send_text(json.dumps({"type": "message", "content": "Hello agent"}))

        # Receive initial responses
        response1 = json.loads(websocket.receive_text())
        assert response1["type"] == "system"

        response2 = json.loads(websocket.receive_text())
        assert response2["type"] == "system"

        # Send stop - construct the JSON directly
        websocket.send_text(json.dumps({"type": "stop", "reason": "Testing stop"}))

        # Should receive system message about stopping
        response = json.loads(websocket.receive_text())
        assert response["type"] == "system"
        assert "Testing stop" in response["content"]


def test_ws_full_integration(client: TestClient, thread, monkeypatch):
    """Test a full integration of the WebSocket with agent responses."""
    thread_id = thread.id

    # Mock the build_idea_agent function to return a predictable agent
    class TestIdeaAgent:
        async def run_mcp_servers(self):
            class MockContextManager:
                async def __aenter__(self):
                    return None

                async def __aexit__(self, *args):
                    return None

            return MockContextManager()

        async def run(self, message, **kwargs):
            # Return a predefined response for testing
            return "This is a test response from the agent."

    # Replace the mock agent created in conftest with our test-specific one
    client.app.state.idea_agent = TestIdeaAgent()  # type: ignore

    # Override the agent_conversation function
    async def test_agent_conversation(queue, message, idea_agent, db, thread_id):
        # Add realistic events to the queue
        await queue.put(SystemEvent(content="Thinking about your request..."))
        await queue.put(SystemEvent(content="Processing..."))
        await queue.put(SystemEvent(content="This is a test response from the agent."))
        await queue.put(DoneEvent())

    monkeypatch.setattr(
        "backend.routers.ws.agent_conversation", test_agent_conversation
    )

    # Connect to the WebSocket
    with client.websocket_connect(f"/ws/{thread_id}") as websocket:
        # Send hello event for protocol negotiation
        hello = HelloEvent(protocol_version="1.0")
        websocket.send_text(hello.model_dump_json())

        # Get the protocol negotiated response
        response = json.loads(websocket.receive_text())
        assert response["type"] == "system"
        assert "Protocol negotiated" in response["content"]

        # Send a test message
        websocket.send_text(
            json.dumps({"type": "message", "content": "Tell me about this project"})
        )

        # Verify responses in expected order
        responses = []
        for _ in range(4):  # Expect 4 messages (3 system + 1 done)
            response = json.loads(websocket.receive_text())
            responses.append(response)

        # Verify the system messages
        assert responses[0]["type"] == "system"
        assert responses[0]["content"] == "Thinking about your request..."

        assert responses[1]["type"] == "system"
        assert responses[1]["content"] == "Processing..."

        assert responses[2]["type"] == "system"
        assert responses[2]["content"] == "This is a test response from the agent."

        # Verify we got a done event
        assert responses[3]["type"] == "done"


def test_ws_auto_thread_creation(client: TestClient, monkeypatch):
    """Test WebSocket endpoint that automatically creates a thread."""

    # Mock agent_conversation to avoid actual processing
    async def mock_agent_conv(*args, **kwargs):
        queue = kwargs.get("queue")
        if queue:
            # Create proper event instances for each message type
            system = SystemEvent(content="Response to auto-created thread")
            done = DoneEvent()

            # Add events to queue
            await queue.put(system)
            await queue.put(done)

    monkeypatch.setattr("backend.routers.ws.agent_conversation", mock_agent_conv)

    # Mock the WebSocket connection
    with client.websocket_connect("/ws") as websocket:
        # First message should be thread creation notification
        thread_info = json.loads(websocket.receive_text())
        assert thread_info["type"] == "thread_created"
        assert "thread_id" in thread_info

        # Send hello event
        hello = HelloEvent(protocol_version="1.0")
        websocket.send_text(hello.model_dump_json())

        # Get the protocol negotiation message
        response = json.loads(websocket.receive_text())
        assert response["type"] == "system"
        assert "Protocol negotiated" in response["content"]

        # Send a message
        websocket.send_text(
            json.dumps({"type": "message", "content": "Test message for new thread"})
        )

        # Should receive our mocked response
        response1 = json.loads(websocket.receive_text())
        assert response1["type"] == "system"
        assert response1["content"] == "Response to auto-created thread"

        # Should receive done event
        response2 = json.loads(websocket.receive_text())
        assert response2["type"] == "done"
