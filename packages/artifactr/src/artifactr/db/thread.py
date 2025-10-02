"""Thread repository for thread-specific database operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from artifactr.db.base import BaseRepository
from artifactr.models.db import Thread

if TYPE_CHECKING:
    from artifactr.db import DatabaseManager

logger = logging.getLogger(__name__)


class ThreadRepository(BaseRepository[Thread]):
    """Repository for thread-specific database operations."""

    def __init__(self, manager: DatabaseManager):
        """Initialize the thread repository."""
        super().__init__(manager, Thread)
