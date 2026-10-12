"""Actors: who published an event or performed a command.

Every envelope is attributed to exactly one actor. The kinds match artifactr's, so a system that
uses both libraries can map one to the other, plus ``source`` for systems that publish events,
such as a monitoring service. Each actor has a ``participant`` key, as in artifactr, that is the
same for everything one participant does: every run of a rule's action is one participant.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from reflexr.core.ids import RuleName, RunId
from reflexr.core.tagged import tag_required


class UserActor(BaseModel):
    """A person, identified by the host application's user id."""

    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)

    kind: Literal["user"] = "user"
    id: str
    name: str | None = None

    @property
    def participant(self) -> str:
        """A key that is equal for every action by the same person."""
        return f"user:{self.id}"

    @property
    def display_name(self) -> str:
        """How this actor is named to people and agents."""
        return self.name or self.id


class AgentActor(BaseModel):
    """An agent or graph running an action for one firing of a rule."""

    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)

    kind: Literal["agent"] = "agent"
    rule: RuleName
    run_id: RunId
    name: str

    @property
    def participant(self) -> str:
        """A key that is equal for every run of the same rule's action."""
        return f"agent:{self.rule}"

    @property
    def display_name(self) -> str:
        """How this actor is named to people and agents."""
        return self.name


class ExternalAgentActor(BaseModel):
    """An agent outside reflexr, connected over MCP.

    A person who connects a client with their own credentials acts through it: their actor is
    its ``on_behalf_of``, and an application's ``authorize`` checks it as them, as artifactr's
    does. A client with credentials of its own acts for no one.
    """

    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)

    kind: Literal["external_agent"] = "external_agent"
    client_id: str
    name: str | None = None
    on_behalf_of: UserActor | None = None
    """The person the client acts for, if it acts for one."""

    @property
    def participant(self) -> str:
        """A key that is equal for every action by the same client."""
        return f"external_agent:{self.client_id}"

    @property
    def display_name(self) -> str:
        """How this actor is named to people and agents."""
        return self.name or self.client_id


class SystemActor(BaseModel):
    """reflexr itself (the reactor, schedules), or the application acting on its own behalf."""

    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)

    kind: Literal["system"] = "system"
    name: str = "reflexr"

    @property
    def participant(self) -> str:
        """A key that is equal for every action by the same system component."""
        return f"system:{self.name}"

    @property
    def display_name(self) -> str:
        """How this actor is named to people and agents."""
        return self.name


class SourceActor(BaseModel):
    """A system that publishes events, such as a monitoring service or a webhook."""

    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)

    kind: Literal["source"] = "source"
    name: str

    @property
    def participant(self) -> str:
        """A key that is equal for every event from the same source."""
        return f"source:{self.name}"

    @property
    def display_name(self) -> str:
        """How this actor is named to people and agents."""
        return self.name


class EvaluatorActor(BaseModel):
    """An evaluator: a judge or decision model whose verdicts are recorded as feedback."""

    model_config = ConfigDict(frozen=True, json_schema_extra=tag_required)

    kind: Literal["evaluator"] = "evaluator"
    name: str
    version: str
    """The evaluator's version, such as a hash of a trained judge, so verdicts never mix."""

    @property
    def participant(self) -> str:
        """A key that is equal for every verdict of the same evaluator version."""
        return f"evaluator:{self.name}@{self.version}"

    @property
    def display_name(self) -> str:
        """How this actor is named to people and agents."""
        return f"{self.name}@{self.version}"


Actor = Annotated[
    UserActor | AgentActor | ExternalAgentActor | SystemActor | SourceActor | EvaluatorActor,
    Field(discriminator="kind"),
]
"""Any actor, discriminated by ``kind``."""
