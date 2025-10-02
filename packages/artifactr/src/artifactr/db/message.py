"""Message repository for message-specific database operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from artifactr.db.base import BaseRepository
from artifactr.models.db import Message

if TYPE_CHECKING:
    from artifactr.db import DatabaseManager

logger = logging.getLogger(__name__)


class MessageRepository(BaseRepository[Message]):
    """Repository for message-specific database operations."""

    def __init__(self, manager: DatabaseManager):
        """Initialize the message repository."""
        super().__init__(manager, Message)
