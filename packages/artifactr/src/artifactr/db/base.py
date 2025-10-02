"""Base manager class for table-specific managers."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from sqlmodel import Session, and_, desc, select

from artifactr.models.db import Identifiable

if TYPE_CHECKING:
    from artifactr.db import DatabaseManager

T = TypeVar("T", bound=Identifiable)

logger = logging.getLogger(__name__)


class BaseRepository(Generic[T]):
    """Base class for repository pattern."""

    def __init__(self, manager: DatabaseManager, model_cls: type[T]):
        """Initialize the base manager.

        Parameters
        ----------
        manager : DatabaseManager
            Reference to the main database manager
        model_cls : type[T]
            The SQLModel class this manager handles
        """
        self.manager = manager
        self.model_cls = model_cls

    @property
    def session(self) -> Session:
        """Get the session for the database manager."""
        return self.manager.session

    def create(self, **kwargs) -> T:
        """Create a new record in the database.

        Parameters
        ----------
        model_instance : T
            The model instance to create

        Returns
        -------
        T
            The created model instance with updated fields
        """
        try:
            model_instance = self.model_cls(**kwargs)
            self.session.add(model_instance)
            self.session.commit()
            self.session.refresh(model_instance)
            logger.info(
                f"Created {type(model_instance).__name__} with id {model_instance.id}"
            )
            return model_instance
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error creating {type(model_instance).__name__}: {e}")
            raise

    def bulk_create(self, instances: list[T]) -> list[T]:
        """Create multiple records in a single transaction.

        Parameters
        ----------
        model_instances : list[T]
            List of model instances to create

        Returns
        -------
        list[T]
            List of created model instances
        """
        try:
            self.session.add_all(instances)
            self.session.commit()
            for instance in instances:
                self.session.refresh(instance)
            logger.info(f"Bulk created {len(instances)} records")
            return instances
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error bulk creating records: {e}")
            raise

    def get_by_id(self, id: int) -> T | None:
        """Get a record by its ID.

        Parameters
        ----------
        id : int
            The ID of the record

        Returns
        -------
        T | None
        The model instance or None if not found
        """
        try:
            result = self.session.get(self.model_cls, id)
            if result:
                logger.debug(f"Found {self.model_cls.__name__} with id {id}")
            else:
                logger.debug(f"No {self.model_cls.__name__} found with id {id}")
            return result
        except Exception as e:
            logger.error(f"Error getting {self.model_cls.__name__} by id {id}: {e}")
            raise

    def get_all(
        self,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Sequence[T]:
        """Get multiple records with optional filtering and pagination.

        Parameters
        ----------
        model_class : type[T]
            The model class to query
        filters : dict[str, Any] | None
            Dictionary of field:value pairs to filter by
        limit : int | None
            Maximum number of records to return
        offset : int | None
            Number of records to skip
        order_by : str | None
            Field name to order by
        order_desc : bool

        Returns
        -------
        list[T]
            List of model instances
        """
        try:
            statement = select(self.model_cls)

            # Apply filters
            if filters:
                conditions = []
                for field, value in filters.items():
                    if hasattr(self.model_cls, field):
                        if isinstance(value, list):
                            conditions.append(getattr(self.model_cls, field).in_(value))
                        else:
                            conditions.append(getattr(self.model_cls, field) == value)
                if conditions:
                    statement = statement.where(and_(*conditions))

            # Apply ordering
            if order_by and hasattr(self.model_cls, order_by):
                order_field = getattr(self.model_cls, order_by)
                if order_desc:
                    statement = statement.order_by(desc(order_field))
                else:
                    statement = statement.order_by(order_field)

            # Apply pagination
            if offset:
                statement = statement.offset(offset)
            if limit:
                statement = statement.limit(limit)

            results = self.session.exec(statement).all()
            logger.debug(f"Found {len(results)} {self.model_cls.__name__} records")
            return results
        except Exception as e:
            logger.error(f"Error getting {self.model_cls.__name__} records: {e}")
            raise

    def update(self, instance: T, data: dict[str, Any]) -> T:
        """Update an existing record.

        Parameters
        ----------
        instance : T
            The model instance to update
        data : dict[str, Any]
            Dictionary of field:value pairs to update

        Returns
        -------
        T
            The updated model instance
        """
        try:
            instance.sqlmodel_update(data)
            self.session.add(instance)
            self.session.commit()
            self.session.refresh(instance)

            logger.info(f"Updated {type(instance).__name__} with id {instance.id}")
            return instance
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error updating {type(instance).__name__}: {e}")
            raise

    def delete(self, id: int) -> bool:
        """Delete a record by its ID.

        Parameters
        ----------
        model_class : type[T]
            The model class to delete from
        id : int
            The ID of the record to delete

        Returns
        -------
        bool
            True if deleted, False if not found
        """
        try:
            instance = self.session.get(self.model_cls, id)
            if instance:
                self.session.delete(instance)
                self.session.commit()
                logger.info(f"Deleted {self.model_cls.__name__} with id {id}")
                return True
            else:
                logger.warning(
                    f"No {self.model_cls.__name__} found with id {id} to delete"
                )
                return False
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error deleting {self.model_cls.__name__} with id {id}: {e}")
            raise
