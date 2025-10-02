"""Thread router for handling thread operations."""

from fastapi import APIRouter, Depends, HTTPException, status

import artifactr.error_code as codes
from artifactr.db import DatabaseManager
from artifactr.dependencies import get_db
from artifactr.models.db import Thread

router = APIRouter()


@router.post("/")
async def create_thread(thread: Thread, db: DatabaseManager = Depends(get_db)):
    """Create a new thread."""
    db.session.add(thread)
    db.session.commit()
    db.session.refresh(thread)
    return thread


@router.get("/{thread_id}")
async def get_thread(thread_id: int, db: DatabaseManager = Depends(get_db)):
    """Get a thread by ID."""
    thread = db.threads.get_by_id(thread_id)
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=codes.THREAD_DOES_NOT_EXIST
        )
    return thread


@router.put("/{thread_id}")
async def update_thread(
    thread_id: int, thread: Thread, db: DatabaseManager = Depends(get_db)
):
    """Update a thread."""
    thread_data = thread.model_dump(exclude_unset=True)

    thread_db = db.threads.get_by_id(thread_id)
    if not thread_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=codes.THREAD_DOES_NOT_EXIST
        )

    return db.threads.update(thread_db, thread_data)


@router.delete("/{thread_id}")
async def delete_thread(thread_id: int, db: DatabaseManager = Depends(get_db)):
    """Delete a thread."""
    thread = db.threads.get_by_id(thread_id)
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=codes.THREAD_DOES_NOT_EXIST
        )
    db.threads.delete(thread_id)
    return {"message": "Thread deleted"}
