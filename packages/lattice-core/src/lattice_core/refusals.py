"""The refusals a REST router documents.

Every router of lattice's packages answers a refused request with the same body, ``Refused``,
and documents the same responses, so a client reads a refusal one way (lattice ADR-0021). The
types are the OpenAPI document's own: moving them here changes none of their names. It needs
pydantic alone: a router passes ``refusals(...)`` to FastAPI's ``APIRouter(responses=...)``.
"""

from typing import Any, Final

from pydantic import BaseModel, ConfigDict

__all__ = ["REFUSALS", "FieldError", "Refused", "RejectionDetail", "refusals"]


class RejectionDetail(BaseModel):
    """A rejection, as REST sends it: its ``type``, its ``message`` and its typed details."""

    model_config = ConfigDict(extra="allow")

    type: str
    message: str


class FieldError(BaseModel):
    """One problem FastAPI found with a request's parameters or body."""

    model_config = ConfigDict(extra="allow")

    loc: list[str | int]
    msg: str
    type: str


class Refused(BaseModel):
    """The body of a refused request.

    ``detail`` is the rejection, the message of a resolver's refusal, or the problems FastAPI
    found with the request.
    """

    detail: RejectionDetail | str | list[FieldError]


def refusals(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """Return the refused responses to document, for ``APIRouter(responses=...)``.

    Each status is described in words of its own, since FastAPI's default is Python's phrase
    for the status, which changes between versions.

    Args:
        *statuses: The HTTP statuses a router's routes refuse with.
    """
    return {status: {"model": Refused, "description": "Refused"} for status in statuses}


REFUSALS: Final = refusals(400, 401, 403, 404, 409, 422)
"""The refused responses artifactr's and reflexr's routes document: a malformed request, no or
a wrong identity, a missing thing, a conflict, and a request that does not validate."""
