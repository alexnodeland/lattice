"""Idea router for handling idea endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

import artifactr.error_code as codes
from artifactr.db import DatabaseManager
from artifactr.dependencies import get_db
from artifactr.models.db import Idea

router = APIRouter()


@router.post("/")
async def create_idea(idea: Idea, db: DatabaseManager = Depends(get_db)):
    """Create a new idea."""
    return db.ideas.create(
        title=idea.title, description=idea.description, user_id=idea.user_id
    )


@router.get("/{idea_id}")
async def get_idea(idea_id: int, db: DatabaseManager = Depends(get_db)):
    """Get an idea by ID."""
    idea = db.ideas.get_by_id(idea_id)
    if not idea:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=codes.IDEA_DOES_NOT_EXIST
        )
    return idea


@router.put("/{idea_id}")
async def update_idea(idea_id: int, idea: Idea, db: DatabaseManager = Depends(get_db)):
    """Update an idea."""
    idea_data = idea.model_dump(exclude_unset=True)

    # Check if idea exists
    existing_idea = db.ideas.get_by_id(idea_id)
    if not existing_idea:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=codes.IDEA_DOES_NOT_EXIST
        )

    return db.ideas.update(existing_idea, idea_data)


@router.delete("/{idea_id}")
async def delete_idea(idea_id: int, db: DatabaseManager = Depends(get_db)):
    """Delete an idea."""
    deleted = db.ideas.delete(idea_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=codes.IDEA_DOES_NOT_EXIST
        )
    return {"message": "Idea deleted"}


@router.get("/")
async def list_ideas(
    limit: int = 10,
    offset: int = 0,
    user_id: int | None = None,
    db: DatabaseManager = Depends(get_db),
):
    """List ideas with optional filtering by user."""
    filters = {}
    if user_id is not None:
        filters["user_id"] = user_id

    ideas = db.ideas.get_all(
        filters=filters if filters else None,
        limit=limit,
        offset=offset,
        order_by="created_at",
        order_desc=True,
    )
    return ideas


@router.get("/recent")
async def get_recent_ideas(limit: int = 10, db: DatabaseManager = Depends(get_db)):
    """Get the most recently created ideas."""
    ideas = db.ideas.get_recent_ideas(limit=limit)
    return ideas


@router.get("/search/title/{search_term}")
async def search_ideas_by_title(
    search_term: str, db: DatabaseManager = Depends(get_db)
):
    """Search ideas by title."""
    ideas = db.ideas.search_ideas_by_title(search_term)
    return ideas


@router.get("/search/description/{search_term}")
async def search_ideas_by_description(
    search_term: str, db: DatabaseManager = Depends(get_db)
):
    """Search ideas by description."""
    ideas = db.ideas.search_ideas_by_description(search_term)
    return ideas


@router.get("/search/{search_term}")
async def search_ideas(search_term: str, db: DatabaseManager = Depends(get_db)):
    """Search ideas by both title and description."""
    ideas = db.ideas.search_ideas(search_term)
    return ideas


@router.get("/user/{user_id}")
async def get_ideas_by_user(
    user_id: int,
    limit: int | None = None,
    db: DatabaseManager = Depends(get_db),
):
    """Get all ideas created by a specific user."""
    # Check if user exists
    user = db.users.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=codes.USER_DOES_NOT_EXIST
        )

    ideas = db.ideas.get_ideas_by_user(user_id, limit=limit)
    return ideas


@router.patch("/{idea_id}/content")
async def update_idea_content(
    idea_id: int,
    title: str | None = None,
    description: str | None = None,
    db: DatabaseManager = Depends(get_db),
):
    """Update an idea's title and/or description."""
    if title is None and description is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of title or description must be provided",
        )

    updated_idea = db.ideas.update_idea_content(
        idea_id, title=title, description=description
    )
    if not updated_idea:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=codes.IDEA_DOES_NOT_EXIST
        )

    return updated_idea
