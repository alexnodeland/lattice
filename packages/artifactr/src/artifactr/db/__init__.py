"""Database manager for centralized database operations."""

from __future__ import annotations

import logging

from sqlmodel import Session

from artifactr.db.document import DocumentRepository
from artifactr.db.idea import IdeaRepository
from artifactr.db.message import MessageRepository
from artifactr.db.thread import ThreadRepository
from artifactr.db.user import UserRepository

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Centralized database manager for all CRUD operations."""

    def __init__(self, session: Session):
        """Initialize the database manager with a session.

        Args:
            session: SQLModel session instance
        """
        self.session = session
        self._users = UserRepository(self)
        self._ideas = IdeaRepository(self)
        self._threads = ThreadRepository(self)
        self._documents = DocumentRepository(self)
        self._messages = MessageRepository(self)

    def __enter__(self) -> DatabaseManager:
        """Enter the context manager."""
        self.session.begin()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Exit the context manager."""
        self.session.close()

    @property
    def users(self) -> UserRepository:
        """Get the user manager."""
        return self._users

    @property
    def ideas(self) -> IdeaRepository:
        """Get the idea manager."""
        return self._ideas

    @property
    def threads(self) -> ThreadRepository:
        """Get the thread manager."""
        return self._threads

    @property
    def documents(self) -> DocumentRepository:
        """Get the document repository."""
        return self._documents

    @property
    def messages(self) -> MessageRepository:
        """Get the message manager."""
        return self._messages

    def commit(self) -> None:
        """Commit the current transaction."""
        self.session.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self.session.rollback()

    def flush(self) -> None:
        """Flush pending changes to the database."""
        self.session.flush()
