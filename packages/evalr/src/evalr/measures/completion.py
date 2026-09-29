"""Task completion: whether a session achieved what the person asked, and how well. Judged."""

from collections.abc import Iterable
from typing import Annotated

from pydantic import BaseModel, Field

from evalr.core import Verdict

__all__ = ["TaskCompletion", "completion_rate"]


class TaskCompletion(BaseModel):
    """Whether the session achieved what the person asked for, and how well."""

    completed: bool = Field(description="The person's request was achieved")
    quality: Annotated[
        int, Field(ge=1, le=5, description="How well it was done, from 1 (poorly) to 5 (very well)")
    ]
    reason: str | None = Field(default=None, description="Why, in a sentence")


def completion_rate(verdicts: Iterable[Verdict[TaskCompletion]]) -> float | None:
    """The share of sessions judged completed; ``None`` for none."""
    values = [v.value.completed for v in verdicts]
    return sum(values) / len(values) if values else None
