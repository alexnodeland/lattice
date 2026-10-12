"""What a read answers: its data, or that its tool is down, or that it isn't configured.

A read never raises for its tool: each admin card calls one read, and a tool that is down fails
only its own cards (lattice RFC-0002).
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Ok[T](BaseModel):
    """The tool answered."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"
    data: T


class Unavailable(BaseModel):
    """The tool didn't answer, or answered with an error; ``reason`` says which."""

    model_config = ConfigDict(frozen=True)

    status: Literal["unavailable"] = "unavailable"
    reason: str


class Unconfigured(BaseModel):
    """The application runs without this tool."""

    model_config = ConfigDict(frozen=True)

    status: Literal["unconfigured"] = "unconfigured"


def reading(data: Any) -> Any:
    """A read's answer, whose data is ``data``: the response model of its route."""
    return Annotated[Ok[data] | Unavailable | Unconfigured, Field(discriminator="status")]
