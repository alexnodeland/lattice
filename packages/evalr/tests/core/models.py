"""Verdict and input types shared by the core tests."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class Thread(BaseModel):
    messages: list[str]


class Helpfulness(BaseModel):
    rating: Annotated[int, Field(ge=1, le=5, description="How much the reply helped")]
    resolved: bool = Field(description="The request was fully addressed")
    category: Literal["billing", "bug", "other"] = "other"
    reason: str | None = None
