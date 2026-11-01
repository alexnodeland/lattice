"""Connections: an outside client a person connected to one of their tenants (grantr ADR-0043).

A person connects a client, such as Claude or Cursor, through portr's OAuth consent page, which
names the client, the tenant and the toolsets it may use (lattice RFC-0014, Decisions P7 and
O12). The connection is grantr's: one tenant each, listed, audited and revoked as keys are, and
read on every call, so revoking one stops it at its next call, not when its token expires.
"""

import re
import secrets
from datetime import datetime
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from grantr.core.ids import TenantId
from grantr.core.subjects import User
from lattice_core.commands import Toolset

CONNECTION_ID: Final = re.compile(r"con_[0-9a-f]{16}")
"""A connection's id: ``con_`` and 16 hex digits."""

CORE: Final[Toolset] = "core"
"""The toolset every connection may use, whatever else it was given."""

ConnectionId = Annotated[str, StringConstraints(pattern=f"^{CONNECTION_ID.pattern}$")]
"""A connection's id, checked."""


def connection_id() -> str:
    """A new connection's id."""
    return f"con_{secrets.token_hex(8)}"


class ClientInfo(BaseModel):
    """The client a connection is through, as its OAuth registration names it."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    client_id: str = Field(min_length=1, max_length=255)
    """Its OAuth ``client_id``, which every token it holds carries."""
    name: str = Field(min_length=1, max_length=200)
    """Its registered name, such as "Claude", which surfaces show as "Alex via Claude"."""
    uri: str | None = Field(default=None, max_length=2000)
    """Its home page, where it registered one."""


class Connection(BaseModel):
    """A client a person connected to one of their tenants, with the toolsets it may use."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    id: ConnectionId
    tenant: TenantId
    """The one tenant it reaches; a second tenant is a second connection."""
    user: User
    """The person who connected it, as whom every call through it is checked."""
    client: ClientInfo
    toolsets: frozenset[Toolset]
    """The toolsets it may use, ``core`` always among them."""
    created_at: datetime
    last_used_at: datetime | None = None
    """When it was last used, at most a few minutes behind."""
    revoked_at: datetime | None = None
    """When it was revoked; a revoked connection refuses every call."""

    @field_validator("toolsets")
    @classmethod
    def _with_core(cls, toolsets: frozenset[Toolset]) -> frozenset[Toolset]:
        return toolsets | frozenset[Toolset]((CORE,))

    @property
    def live(self) -> bool:
        """Whether it may be used: it hasn't been revoked."""
        return self.revoked_at is None
