from unittest.mock import MagicMock, patch

import pytest

from artifactr.db import DatabaseManager
from artifactr.models.db import Idea
from artifactr.services.mcp import (
    create_idea,
    delete_idea,
    get_idea,
    list_ideas,
    update_idea,
)


@pytest.fixture
def mock_db_manager():
    """Mock database manager for testing."""
    # Create a mock that acts as both the function return and context manager
    mock_db = MagicMock(spec=DatabaseManager)

    # Make it work as a context manager
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=None)

    with patch("backend.services.mcp.get_db_direct", return_value=mock_db):
        yield mock_db


@pytest.fixture
def sample_idea(mock_db_manager):
    """Create a sample idea for testing."""
    idea = Idea(
        id=1,
        title="Test Idea",
        description="Test Description",
        user_id=1,
    )
    # Configure the mock to return this idea
    mock_db_manager.ideas.get_by_id.return_value = idea
    mock_db_manager.ideas.get_all.return_value = [idea]
    mock_db_manager.ideas.create.return_value = idea
    mock_db_manager.ideas.update.return_value = idea
    mock_db_manager.ideas.delete.return_value = True
    return idea


@pytest.mark.asyncio
async def test_get_idea_success(mock_db_manager, sample_idea):
    """Test getting an idea successfully."""
    # Execute
    result = await get_idea(sample_idea.id)

    # Verify
    assert result["id"] == sample_idea.id
    assert result["title"] == sample_idea.title
    assert result["description"] == sample_idea.description


@pytest.mark.asyncio
async def test_get_idea_not_found(mock_db_manager):
    """Test getting an idea that doesn't exist."""
    # Configure mock to return None for non-existent idea
    mock_db_manager.ideas.get_by_id.return_value = None

    # Execute
    result = await get_idea(999)

    # Verify
    assert "error" in result
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_get_idea_exception(mock_db_manager):
    """Test getting an idea with database exception."""
    # Configure mock to raise an exception
    mock_db_manager.ideas.get_by_id.side_effect = Exception("Database error")

    # Execute
    result = await get_idea(1)

    # Verify
    assert "error" in result
    assert "Database error" in result["error"]


@pytest.mark.asyncio
async def test_list_ideas_success(mock_db_manager, sample_idea):
    """Test listing all ideas successfully."""
    # Execute
    result = await list_ideas()

    # Verify
    assert "ideas" in result
    assert len(result["ideas"]) > 0


@pytest.mark.asyncio
async def test_list_ideas_exception(mock_db_manager):
    """Test listing ideas with database exception."""
    # Configure mock to raise an exception
    mock_db_manager.ideas.get_all.side_effect = Exception("Database error")

    # Execute
    result = await list_ideas()

    # Verify
    assert "error" in result
    assert "Database error" in result["error"]
    assert "ideas" in result
    assert result["ideas"] == []


@pytest.mark.asyncio
async def test_create_idea_success(mock_db_manager):
    """Test creating an idea successfully."""
    # Create a proper idea object to return
    created_idea = Idea(
        id=2,
        title="New Test Title",
        description="New Test Description",
        user_id=1,
    )
    mock_db_manager.ideas.create.return_value = created_idea

    # Execute
    result = await create_idea("New Test Title", "New Test Description", 1)

    # Verify
    assert result["id"] == 2
    assert result["title"] == "New Test Title"
    assert result["description"] == "New Test Description"


@pytest.mark.asyncio
async def test_create_idea_exception(mock_db_manager):
    """Test creating an idea with database exception."""
    # Configure mock to raise an exception
    mock_db_manager.ideas.create.side_effect = Exception("Database error")

    # Execute
    result = await create_idea("Test Title", "Test Description", 1)

    # Verify
    assert "error" in result
    assert "Database error" in result["error"]


@pytest.mark.asyncio
async def test_update_idea_success(mock_db_manager, sample_idea):
    """Test updating an idea successfully."""
    # Create updated idea
    updated_idea = Idea(
        id=sample_idea.id,
        title="Updated Title",
        description=sample_idea.description,
        user_id=sample_idea.user_id,
    )
    mock_db_manager.ideas.update.return_value = updated_idea

    # Execute
    result = await update_idea(sample_idea.id, title="Updated Title")

    # Verify
    assert result["id"] == sample_idea.id
    assert result["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_update_idea_not_found(mock_db_manager):
    """Test updating an idea that doesn't exist."""
    # Configure mock to return None for non-existent idea
    mock_db_manager.ideas.get_by_id.return_value = None

    # Execute
    result = await update_idea(999, title="Updated Title")

    # Verify
    assert "error" in result
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_update_idea_exception(mock_db_manager):
    """Test updating an idea with database exception."""
    # Configure mock to raise an exception
    mock_db_manager.ideas.get_by_id.side_effect = Exception("Database error")

    # Execute
    result = await update_idea(1, title="Updated Title")

    # Verify
    assert "error" in result
    assert "Database error" in result["error"]


@pytest.mark.asyncio
async def test_delete_idea_success(mock_db_manager, sample_idea):
    """Test deleting an idea successfully."""
    # Execute
    result = await delete_idea(sample_idea.id)

    # Verify
    assert "success" in result
    assert result["success"] is True


@pytest.mark.asyncio
async def test_delete_idea_not_found(mock_db_manager):
    """Test deleting an idea that doesn't exist."""
    # Configure mock to return False for non-existent idea
    mock_db_manager.ideas.delete.return_value = False

    # Execute
    result = await delete_idea(999)

    # Verify
    assert "error" in result
    assert "not found" in result["error"]
