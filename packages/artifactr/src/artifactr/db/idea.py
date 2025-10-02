"""Idea repository for idea-specific database operations."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import desc, func, or_, select

from artifactr.db.base import BaseRepository
from artifactr.models.db import Idea

if TYPE_CHECKING:
    from artifactr.db import DatabaseManager

logger = logging.getLogger(__name__)


class IdeaRepository(BaseRepository[Idea]):
    """Repository for idea-specific database operations."""

    def __init__(self, manager: DatabaseManager):
        """Initialize the idea repository."""
        super().__init__(manager, Idea)

    def get_recent_ideas(self, limit: int = 10) -> Sequence[Idea]:
        """Get the most recently created ideas.

        Parameters
        ----------
        limit : int
            Maximum number of ideas to return (default: 10)

        Returns
        -------
        Sequence[Idea]
            List of ideas ordered by creation date (newest first)
        """
        try:
            statement = select(Idea).order_by(desc(Idea.created_at)).limit(limit)
            results = self.session.exec(statement).all()
            logger.debug(f"Found {len(results)} recent ideas")
            return results
        except Exception as e:
            logger.error(f"Error getting recent ideas: {e}")
            raise

    def search_ideas_by_title(self, search_term: str) -> Sequence[Idea]:
        """Search ideas by title using case-insensitive partial matching.

        Parameters
        ----------
        search_term : str
            The term to search for in idea titles

        Returns
        -------
        Sequence[Idea]
            List of ideas with titles containing the search term
        """
        try:
            statement = (
                select(Idea)
                .where(func.lower(Idea.title).like(f"%{search_term.lower()}%"))
                .order_by(desc(Idea.created_at))
            )
            results = self.session.exec(statement).all()
            logger.debug(
                f"Found {len(results)} ideas matching title search: {search_term}"
            )
            return results
        except Exception as e:
            logger.error(f"Error searching ideas by title: {e}")
            raise

    def search_ideas_by_description(self, search_term: str) -> Sequence[Idea]:
        """Search ideas by description using case-insensitive partial matching.

        Parameters
        ----------
        search_term : str
            The term to search for in idea descriptions

        Returns
        -------
        Sequence[Idea]
            List of ideas with descriptions containing the search term
        """
        try:
            statement = (
                select(Idea)
                .where(func.lower(Idea.description).like(f"%{search_term.lower()}%"))
                .order_by(desc(Idea.created_at))
            )
            results = self.session.exec(statement).all()
            logger.debug(
                f"Found {len(results)} ideas matching description search: {search_term}"
            )
            return results
        except Exception as e:
            logger.error(f"Error searching ideas by description: {e}")
            raise

    def search_ideas(self, search_term: str) -> Sequence[Idea]:
        """Search ideas by both title and description using case-insensitive partial matching.

        Parameters
        ----------
        search_term : str
            The term to search for in both title and description

        Returns
        -------
        Sequence[Idea]
            List of ideas with title or description containing the search term
        """
        try:
            search_lower = search_term.lower()
            statement = (
                select(Idea)
                .where(
                    or_(
                        func.lower(Idea.title).like(f"%{search_lower}%"),
                        func.lower(Idea.description).like(f"%{search_lower}%"),
                    )
                )
                .order_by(desc(Idea.created_at))
            )
            results = self.session.exec(statement).all()
            logger.debug(f"Found {len(results)} ideas matching search: {search_term}")
            return results
        except Exception as e:
            logger.error(f"Error searching ideas: {e}")
            raise

    def get_ideas_by_user(
        self, user_id: int, limit: int | None = None
    ) -> Sequence[Idea]:
        """Get all ideas created by a specific user.

        Parameters
        ----------
        user_id : int
            The ID of the user whose ideas to retrieve
        limit : int | None
            Maximum number of ideas to return (optional)

        Returns
        -------
        Sequence[Idea]
            List of ideas created by the user, ordered by creation date (newest first)
        """
        try:
            statement = (
                select(Idea)
                .where(Idea.user_id == user_id)
                .order_by(desc(Idea.created_at))
            )
            if limit is not None:
                statement = statement.limit(limit)

            results = self.session.exec(statement).all()
            logger.debug(f"Found {len(results)} ideas for user {user_id}")
            return results
        except Exception as e:
            logger.error(f"Error getting ideas by user {user_id}: {e}")
            raise

    def update_idea_content(
        self, idea_id: int, title: str | None = None, description: str | None = None
    ) -> Idea | None:
        """Update an idea's title and/or description.

        Parameters
        ----------
        idea_id : int
            The ID of the idea to update
        title : str | None
            New title for the idea (optional)
        description : str | None
            New description for the idea (optional)

        Returns
        -------
        Idea | None
            The updated idea or None if not found
        """
        try:
            idea = self.session.get(Idea, idea_id)
            if not idea:
                logger.warning(f"No idea found with id {idea_id}")
                return None

            # Update fields if provided
            if title is not None:
                idea.title = title
            if description is not None:
                idea.description = description

            idea.updated_at = datetime.now()

            self.session.add(idea)
            self.session.commit()
            self.session.refresh(idea)

            logger.info(f"Updated content for idea {idea_id}")
            return idea
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error updating idea content for id {idea_id}: {e}")
            raise
