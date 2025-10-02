"""MCP servers for the backend."""

from datetime import datetime

from artifactr.dependencies import get_db_direct, get_logger
from artifactr.main import mcp_server_idea

logger = get_logger()


@mcp_server_idea.tool()
async def get_idea(idea_id: int) -> dict:
    """Get an idea by ID.

    Parameters
    ----------
        idea_id: The ID of the idea to retrieve

    Returns
    -------
    dict
        The idea or an error message
    """
    try:
        with get_db_direct() as db:
            idea = db.ideas.get_by_id(idea_id)
            if idea is None:
                return {"error": f"Idea with ID {idea_id} not found"}

            return idea.model_dump()
    except Exception as e:
        logger.error(f"Error retrieving idea: {e}")
        return {"error": f"Database error: {e!s}"}


@mcp_server_idea.tool()
async def list_ideas() -> dict:
    """List all available ideas.

    Returns
    -------
    dict
        A dictionary containing all the ideas
    """
    try:
        with get_db_direct() as db:
            ideas = db.ideas.get_all()
            return {"ideas": [idea.model_dump() for idea in ideas]}
    except Exception as e:
        logger.error(f"Error listing ideas: {e}")
        return {"error": f"Database error: {e!s}", "ideas": []}


@mcp_server_idea.tool()
async def create_idea(title: str, description: str, user_id: int) -> dict:
    """Create a new idea.

    Parameters
    ----------
        title: The title of the idea
        description: The description of the idea
        user_id: The ID of the user who created the idea

    Returns
    -------
        The created idea
    """
    try:
        with get_db_direct() as db:
            now = datetime.now()

            idea = db.ideas.create(
                title=title,
                description=description,
                created_at=now,
                updated_at=now,
                user_id=user_id,
            )

            return idea.model_dump()
    except Exception as e:
        logger.error(f"Error creating idea: {e}")
        return {"error": f"Database error: {e!s}"}


@mcp_server_idea.tool()
async def update_idea(
    idea_id: int, title: str | None = None, description: str | None = None
) -> dict:
    """Update an existing idea.

    Parameters
    ----------
    idea_id : int
        The ID of the idea to update
    title : str | None
        The new title (optional)
    description : str | None
        The new description (optional)

    Returns
    -------
        The updated idea or an error message
    """
    try:
        with get_db_direct() as db:
            idea = db.ideas.get_by_id(idea_id)
            if idea is None:
                return {"error": f"Idea with ID {idea_id} not found"}

            # Prepare update data
            update_data = {}
            if title is not None:
                update_data["title"] = title
            if description is not None:
                update_data["description"] = description

            if update_data:
                update_data["updated_at"] = datetime.now()
                updated_idea = db.ideas.update(idea, update_data)
                return updated_idea.model_dump()
            else:
                return idea.model_dump()  # No changes made

    except Exception as e:
        logger.error(f"Error updating idea: {e}")
        return {"error": f"Database error: {e!s}"}


@mcp_server_idea.tool()
async def delete_idea(idea_id: int) -> dict:
    """Delete an idea.

    Parameters
    ----------
    idea_id : int
        The ID of the idea to delete

    Returns
    -------
        Success message or error message
    """
    try:
        with get_db_direct() as db:
            success = db.ideas.delete(idea_id)
            if not success:
                return {"error": f"Idea with ID {idea_id} not found"}

            return {"success": True, "message": f"Idea with ID {idea_id} deleted"}
    except Exception as e:
        logger.error(f"Error deleting idea: {e}")
        return {"error": f"Database error: {e!s}"}
