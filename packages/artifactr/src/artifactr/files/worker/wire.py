"""What the application and the worker say to each other, over HTTP, one request a call.

A call's file is the request's body, and the call itself is JSON in its `Worker-Call` header,
with the deadline the caller gives it. A reply is JSON, but a render's, which is its PNG; a call
that fails replies 422 with how, a `Failed`.
"""

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from artifactr.files.app import AppCommand, Failure, Inspection, Talk

CALL: Final = "Worker-Call"
"""The header that carries a call, as JSON."""

CALL_LIMIT: Final = 64 << 10
"""The most bytes a call's JSON may hold, which the worker's server reads a request's head up to:
a longer batch of commands is refused as too large before it is sent."""


class _Call(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    deadline: float = Field(gt=0)


class ApplyCall(_Call):
    """Apply a batch of commands to the body's file, or to a new one if the body is empty."""

    commands: list[AppCommand]


class InspectCall(_Call):
    """Read the body's file."""


class RenderCall(_Call):
    """Render one page of the body's file, from 1, as a PNG."""

    page: int = Field(ge=1)
    scale: float = Field(gt=0)


class CommandsCall(BaseModel):
    """Find the commands that match a query; it has no body, and the worker's own deadline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str


class Hello(BaseModel):
    """The app the worker runs, as the application's `Worker` presents it."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    build: str | None
    talk: Talk
    integration: str


class AppliedReply(BaseModel):
    """A batch applied: the new file, in base64, and what the app read from it."""

    model_config = ConfigDict(ser_json_bytes="base64", val_json_bytes="base64")

    content: bytes
    inspection: Inspection


class Failed(BaseModel):
    """How a call failed, as [`AppFailed`][artifactr.files.app.AppFailed] tells it."""

    failure: Failure
    message: str
