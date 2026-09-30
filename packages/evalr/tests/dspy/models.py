"""Types shared by the DSPy tests."""

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class Thread(BaseModel):
    request: str = Field(description="What the person asked for")
    reply: str


class Tone(Enum):
    WARM = "warm"
    COLD = "cold"


class Helpfulness(BaseModel):
    """Whether the reply helped the person."""

    rating: Annotated[int, Field(ge=1, le=5, description="How much the reply helped")]
    resolved: bool = Field(description="The request was fully addressed")
    category: Literal["billing", "bug", "other"] = "other"
    tone: Tone | None = None
    share: float = Field(default=0.5, ge=0.0, le=1.0)
    reason: str | None = None


THREAD = Thread(request="I was charged twice", reply="I refunded the duplicate charge")
