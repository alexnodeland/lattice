import json

from fastapi import status
from fastapi.testclient import TestClient

from src.backend.models.events import DoneEvent, SystemEvent


def test_agent_stream_endpoint(client: TestClient, thread, monkeypatch):
    """Test the agent streaming endpoint."""
    thread_id = thread.id

    # Mock agent_conversation to avoid actual processing
    async def mock_agent_conv(*args, **kwargs):
        queue = kwargs.get("queue")
        if queue:
            # Use event models that match the expected output
            await queue.put(SystemEvent(content="Thinking..."))
            await queue.put(SystemEvent(content="Response message"))
            await queue.put(DoneEvent())

    monkeypatch.setattr("backend.routers.agent.agent_conversation", mock_agent_conv)

    # Make request to streaming endpoint
    response = client.post(f"/agent/{thread_id}", json={"message": "Hello agent"})

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    # Parse the SSE streaming response
    # SSE format is "data: <json>\n\n" for each event
    sse_chunks = response.text.strip().split("\n\n")
    events = []
    for chunk in sse_chunks:
        if chunk.startswith("data: "):
            json_data = chunk[6:]  # Remove "data: " prefix
            events.append(json.loads(json_data))

    # Verify the sequence of events
    assert len(events) == 3
    assert events[0]["type"] == "system"
    assert events[0]["content"] == "Thinking..."
    assert events[1]["type"] == "system"
    assert events[1]["content"] == "Response message"
    assert events[2]["type"] == "done"


def test_agent_thread_not_found(client: TestClient):
    """Test streaming endpoint with non-existent thread ID."""
    response = client.post("/agent/999999", json={"message": "Hello agent"})

    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert "detail" in data


def test_agent_invalid_request(client: TestClient, thread):
    """Test streaming endpoint with invalid request body."""
    thread_id = thread.id

    # Missing required 'message' field
    response = client.post(f"/agent/{thread_id}", json={})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
