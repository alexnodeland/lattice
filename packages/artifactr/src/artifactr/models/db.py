"""Database models.

Notes
-----
- Do not use future imports because it breaks the ability for SQLModel to
  introspect the database schema.
"""

from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship, SQLModel


class Identifiable(SQLModel):
    """A base model for all database models."""

    id: int | None = Field(default=None, primary_key=True)


class User(Identifiable, table=True):
    """A user."""

    name: str
    email: str = Field(unique=True)
    ideas: list["Idea"] = Relationship(back_populates="user")


class Idea(Identifiable, table=True):
    """An idea."""

    title: str
    description: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    user_id: int | None = Field(default=None, foreign_key="user.id")
    user: User | None = Relationship(back_populates="ideas")


class Thread(Identifiable, table=True, extend_existing=True):
    """A thread."""

    title: str
    description: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    messages: list["Message"] = Relationship(back_populates="thread")

    @property
    def time_ordered_messages(self) -> list["Message"]:
        """Get the messages in time order."""
        return sorted(self.messages, key=lambda m: m.timestamp)


class Document(Identifiable, table=True, extend_existing=True):
    """A document."""

    title: str
    description: str
    created_at: datetime = Field(default_factory=datetime.now)


class Message(Identifiable, table=True, extend_existing=True):
    """A message."""

    type: str = Field(default="message")
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    meta: dict | None = Field(default=None, sa_column=Column(JSON))
    thread_id: int | None = Field(default=None, foreign_key="thread.id")
    thread: Thread | None = Relationship(back_populates="messages")
