"""Document repository for document-specific database operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from artifactr.db.base import BaseRepository
from artifactr.models.db import Document

if TYPE_CHECKING:
    from artifactr.db import DatabaseManager

logger = logging.getLogger(__name__)


class DocumentRepository(BaseRepository[Document]):
    """Repository for document-specific database operations."""

    def __init__(self, manager: DatabaseManager):
        """Initialize the document repository."""
        super().__init__(manager, Document)
