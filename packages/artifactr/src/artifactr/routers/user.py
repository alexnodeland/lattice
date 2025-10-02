"""User router."""

from fastapi import APIRouter, Depends, HTTPException, status

import artifactr.error_code as codes
from artifactr.db import DatabaseManager
from artifactr.dependencies import get_db
from artifactr.models.db import User

router = APIRouter()


@router.post("/")
async def create_user(user: User, db: DatabaseManager = Depends(get_db)):
    """Create a new user."""
    return db.users.create(name=user.name, email=user.email)


@router.get("/{user_id}")
async def get_user(user_id: int, db: DatabaseManager = Depends(get_db)):
    """Get a user by ID."""
    user = db.users.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=codes.USER_DOES_NOT_EXIST
        )
    return user


@router.put("/{user_id}")
async def update_user(user_id: int, user: User, db: DatabaseManager = Depends(get_db)):
    """Update a user."""
    data = user.model_dump(exclude_unset=True)

    existing_user = db.users.get_by_id(user_id)
    if not existing_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=codes.USER_DOES_NOT_EXIST
        )

    try:
        return db.users.update(existing_user, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{user_id}")
async def delete_user(user_id: int, db: DatabaseManager = Depends(get_db)):
    """Delete a user."""
    deleted = db.users.delete(user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=codes.USER_DOES_NOT_EXIST
        )
    return {"message": "User deleted"}


@router.get("/")
async def list_users(
    limit: int = 10, offset: int = 0, db: DatabaseManager = Depends(get_db)
):
    """List users with pagination."""
    users = db.users.get_all(limit=limit, offset=offset, order_by="name")
    return users


@router.get("/search/by-email/{email}")
async def get_user_by_email(email: str, db: DatabaseManager = Depends(get_db)):
    """Get a user by their email address."""
    user = db.users.get_by_email(email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=codes.USER_DOES_NOT_EXIST
        )
    return user


@router.get("/search/by-name/{pattern}")
async def search_users_by_name(pattern: str, db: DatabaseManager = Depends(get_db)):
    """Search users by name pattern."""
    users = db.users.get_by_name_pattern(pattern)
    return users


@router.get("/{user_id}/ideas")
async def get_user_ideas(user_id: int, db: DatabaseManager = Depends(get_db)):
    """Get all ideas created by a specific user."""
    # Check if user exists
    user = db.users.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=codes.USER_DOES_NOT_EXIST
        )
    return user.ideas
