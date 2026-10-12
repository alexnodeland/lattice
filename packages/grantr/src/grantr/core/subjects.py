"""Subjects: who acts, and who is granted a role.

A subject is the principal a check is asked about. A grantee is what a grant names: any subject
but the agent, which holds nothing, or a group. Each is a frozen model, discriminated by
``kind``, so it can be stored, compared and hashed.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from grantr.core.ids import PrincipalId, UserId, WorkspaceId


class User(BaseModel):
    """A person, by their identity provider's id."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["user"] = "user"
    id: UserId


class ServicePrincipal(BaseModel):
    """A tenant's non-human principal: an integration, an MCP client or the application."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["service_principal"] = "service_principal"
    id: PrincipalId


class RulePrincipal(BaseModel):
    """A reflexr rule, named by its workspace and rule: its runs act as it."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["rule"] = "rule"
    workspace: WorkspaceId
    rule: str


class Agent(BaseModel):
    """A turn's agent acting for no one. It holds nothing, and can't be granted a role."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["agent"] = "agent"


class Group(BaseModel):
    """A tenant's named set of users and service principals, granted roles like a subject."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["group"] = "group"
    id: str


type Subject = Annotated[
    User | ServicePrincipal | RulePrincipal | Agent, Field(discriminator="kind")
]
"""Who a check is asked about."""

type Member = Annotated[User | ServicePrincipal, Field(discriminator="kind")]
"""Who belongs to a tenant, and to its groups."""

type Grantee = Annotated[
    User | ServicePrincipal | RulePrincipal | Group, Field(discriminator="kind")
]
"""Who a grant names."""
