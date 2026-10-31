"""Taint: whether a turn, a run or a code session has read untrusted content, and what caused it.

A taint is :class:`Clean`, or :class:`Tainted` with its causes, each a capability whose result
was read or an event that was matched, and when, and the hosts it has seen. It is carried on a
call's :class:`~lattice_core.capabilities.CallContext`, set after a capability whose effects
read untrusted content is called, carried to the runs and sessions started from a tainted one,
and cleared only by a person (lattice RFC-0011).

This module holds only the contract the capability registry, approvals and egress read. What a
taint allows, a workspace's ``TaintPolicy``, is not declared here.
"""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lattice_core.schema import tag_required

__all__ = ["Cause", "Clean", "Taint", "Tainted"]


class Cause(BaseModel):
    """What tainted a turn, a run or a session: a capability or an event, and when.

    Raises:
        ValueError: Unless exactly one of ``capability`` and ``event`` is given.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    capability: str | None = None
    """The name of the capability whose result was read."""
    event: str | None = None
    """The id of the event whose untrusted content was read, such as a matched envelope's."""
    at: datetime
    """When it was read."""

    @model_validator(mode="after")
    def _one_cause(self) -> Self:
        if (self.capability is None) == (self.event is None):
            raise ValueError("a cause is a capability or an event, exactly one")
        return self


class Clean(BaseModel):
    """Nothing untrusted has been read."""

    model_config = ConfigDict(
        frozen=True, use_attribute_docstrings=True, json_schema_extra=tag_required
    )

    state: Literal["clean"] = "clean"


class Tainted(BaseModel):
    """Untrusted content has been read: by what and when, and the hosts seen since."""

    model_config = ConfigDict(
        frozen=True, use_attribute_docstrings=True, json_schema_extra=tag_required
    )

    state: Literal["tainted"] = "tainted"
    causes: tuple[Cause, ...] = Field(min_length=1)
    """What tainted it, in the order it was read."""
    seen_hosts: frozenset[str] = frozenset()
    """The hosts that appeared in what was read, the only ones a narrowed call may reach."""


type Taint = Annotated[Clean | Tainted, Field(discriminator="state")]
"""A taint, discriminated by ``state``: :class:`Clean` or :class:`Tainted`."""
