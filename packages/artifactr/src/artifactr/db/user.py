"""User repository for user-specific database operations."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from sqlmodel import select

from artifactr.db.base import BaseRepository
from artifactr.models.db import User

if TYPE_CHECKING:
    from artifactr.db import DatabaseManager

logger = logging.getLogger(__name__)


class UserRepository(BaseRepository[User]):
    """Repository for user-specific database operations."""

    def __init__(self, manager: DatabaseManager):
        """Initialize the user repository."""
        super().__init__(manager, User)

    def get_by_email(self, email: str) -> User | None:
        """Get a user by their email address."""
        return self.session.exec(select(User).where(User.email == email)).first()

    def get_by_name_pattern(self, pattern: str) -> Sequence[User]:
        """Get users by name pattern."""
        return self.session.exec(
            select(User).where(User.name.ilike(f"%{pattern}%"))  # type: ignore
        ).all()
