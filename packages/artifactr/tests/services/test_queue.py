import asyncio

import pytest

from artifactr.models.events import (
    DoneEvent,
    ErrorEvent,
    SystemEvent,
    TokenEvent,
)
from artifactr.services.queue import PrioritizedQueue


@pytest.fixture
def queue():
    """Create a prioritized queue for testing."""
    return PrioritizedQueue(maxsize=5)


@pytest.mark.asyncio
async def test_queue_initialization(queue):
    """Test queue initialization."""
    assert queue.empty()


@pytest.mark.asyncio
async def test_high_priority_events(queue):
    """Test that high priority events are processed first."""
    # Add a mix of high and low priority events
    await queue.put(TokenEvent(content="low priority"))
    await queue.put(SystemEvent(content="high priority 1"))
    await queue.put(TokenEvent(content="low priority 2"))
    await queue.put(ErrorEvent(content="high priority 2"))

    # High priority events should come out first
    event1 = await queue.get()
    assert isinstance(event1, SystemEvent)
    assert event1.content == "high priority 1"

    event2 = await queue.get()
    assert isinstance(event2, ErrorEvent)
    assert event2.content == "high priority 2"

    # Then low priority events
    event3 = await queue.get()
    assert isinstance(event3, TokenEvent)
    assert event3.content == "low priority"

    event4 = await queue.get()
    assert isinstance(event4, TokenEvent)
    assert event4.content == "low priority 2"


@pytest.mark.asyncio
async def test_queue_overflow(queue):
    """Test queue behavior when it reaches its capacity."""
    # Fill the low priority queue to capacity
    for i in range(5):
        await queue.put(TokenEvent(content=f"token {i}"))

    # Add one more low priority event, which should replace the oldest one
    await queue.put(TokenEvent(content="overflow token"))

    # Get all events and verify the first one was dropped
    events = []
    while not queue.empty():
        events.append(await queue.get())

    contents = [e.content for e in events]
    assert "token 0" not in contents
    assert "overflow token" in contents


@pytest.mark.asyncio
async def test_queue_timeout(queue, monkeypatch):
    """Test queue behavior when put operation times out."""
    # Set a very short timeout
    monkeypatch.setattr(queue, "timeout", 0.001)

    # Fill the queue
    for i in range(5):
        await queue.put(TokenEvent(content=f"token {i}"))

    # Wait longer than the timeout
    await asyncio.sleep(0.002)

    # Try to add one more item
    await queue.put(TokenEvent(content="timeout token"))

    # The oldest item should have been dropped
    events = []
    while not queue.empty():
        events.append(await queue.get())

    contents = [e.content for e in events]
    assert "timeout token" in contents


@pytest.mark.asyncio
async def test_empty_check(queue):
    """Test the empty method."""
    assert queue.empty()

    await queue.put(TokenEvent(content="test"))
    assert not queue.empty()

    await queue.get()
    assert queue.empty()


@pytest.mark.asyncio
async def test_done_event_priority(queue):
    """Test that DoneEvent is treated as high priority."""
    await queue.put(TokenEvent(content="low priority"))
    await queue.put(DoneEvent())

    event = await queue.get()
    assert isinstance(event, DoneEvent)
