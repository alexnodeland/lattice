"""Feedback types declared as artifactr's and reflexr's are, for the score config fixture.

``score_configs.json`` holds the configs and scores the libraries' own copies of the mapping gave
these types before evalr's replaced them (ADR-0011). ``test_score_configs.py`` checks evalr's
mapping gives the same, so the configs the libraries create in Langfuse stay as they were.
"""

from enum import Enum, IntEnum, StrEnum
from typing import Annotated, Literal

import annotated_types
from pydantic import BaseModel, Field, PositiveInt


class Helpfulness(BaseModel):
    """The libraries' test type: a rating and a reason."""

    rating: Annotated[int, Field(ge=1, le=5)]
    reason: str | None = None


class Correctness(StrEnum):
    RIGHT = "right"
    WRONG = "wrong"


class Accuracy(BaseModel):
    """The libraries' other test type: one field of each kind."""

    correct: bool
    verdict: Correctness = Correctness.RIGHT
    tone: Literal["formal", "casual"] = "formal"
    confidence: Annotated[float, Field(ge=0, le=1)] = 1.0


class Review(BaseModel):
    """Optional, constrained and unscorable fields, as the libraries test them."""

    effort: Annotated[int, Field(gt=0, lt=10, description="How hard it was")] | None = None
    tags: tuple[str, ...] = ()
    either: int | str = 0
    unbounded: float = 0.0


class Colour(Enum):
    RED = "red"
    GREEN = "green"


class Priority(IntEnum):
    LOW = 1
    HIGH = 2


class Everything(BaseModel):
    """Every way the libraries' feedback types declare a field."""

    resolved: bool = Field(description="The request was fully addressed")
    maybe: bool | None = None
    rating: int = Field(ge=1, le=5, description="How much it helped")
    count: int = 0
    at_least: int = Field(default=0, ge=0)
    at_most: Annotated[float, Field(le=10)] = 0.0
    positive: PositiveInt = 1
    share: float = Field(default=0.5, ge=0.0, le=1.0)
    ratio: Annotated[float, Field(gt=0.0, lt=2.5)] = 1.0
    interval: Annotated[int, annotated_types.Interval(ge=1, le=7)] | None = None
    grouped: Annotated[int, annotated_types.Ge(0), annotated_types.Le(100)] = 0
    level: Literal[1, 2, 3] = 1
    category: Literal["billing", "bug", "other"] = "other"
    maybe_category: Literal["a", "b"] | None = None
    colour: Colour = Colour.RED
    priority: Priority = Priority.LOW
    verdict: Correctness | None = None
    note: Annotated[str, Field(max_length=900, description="A short note")] = ""
    inner: Annotated[str, Field(description="Described inside the optional")] | None = None
    outer: Annotated[str | None, Field(description="Described outside")] = None
    both: Annotated[int, Field(ge=0, description="inner")] | None = Field(
        default=None, description="outer"
    )
    items: list[str] = Field(default_factory=list[str])
    nested: Accuracy | None = None
    mapping: dict[str, int] = Field(default_factory=dict[str, int])
    number: int | float = 0


TYPES: dict[str, type[BaseModel]] = {
    "helpfulness": Helpfulness,
    "accuracy": Accuracy,
    "review_for_scores": Review,
    "everything": Everything,
}
"""Each type by the name the libraries' tests register it under."""
