"""Actors: who did something.

Every event in a workspace is attributed to exactly one actor. Actors are compared by
*participant*, not by value: every run of a thread's agent is the same participant, so the
agent is not told about its own changes from an earlier run.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from artifactr.core.ids import RunId, ThreadId


class UserActor(BaseModel):
    """A person, identified by the host application's user id."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["user"] = "user"
    id: str
    name: str | None = None

    @property
    def participant(self) -> str:
        """A key that is equal for every action by the same participant."""
        return f"user:{self.id}"

    @property
    def display_name(self) -> str:
        """How this actor is named in change notes."""
        return self.name or self.id


class AgentActor(BaseModel):
    """The built-in agent of one thread, acting within one run."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["agent"] = "agent"
    thread_id: ThreadId
    run_id: RunId | None = None
    name: str = "assistant"

    @property
    def participant(self) -> str:
        """A key that is equal for every run of the same thread's agent."""
        return f"agent:{self.thread_id}"

    @property
    def display_name(self) -> str:
        """How this actor is named in change notes."""
        return self.name


class ExternalAgentActor(BaseModel):
    """An agent outside artifactr, connected over MCP."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["external_agent"] = "external_agent"
    client_id: str
    name: str | None = None

    @property
    def participant(self) -> str:
        """A key that is equal for every action by the same client."""
        return f"external_agent:{self.client_id}"

    @property
    def display_name(self) -> str:
        """How this actor is named in change notes."""
        return self.name or self.client_id


class SystemActor(BaseModel):
    """The application itself, for automated changes."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["system"] = "system"
    name: str = "system"

    @property
    def participant(self) -> str:
        """A key that is equal for every action by the same system component."""
        return f"system:{self.name}"

    @property
    def display_name(self) -> str:
        """How this actor is named in change notes."""
        return self.name


class EvaluatorActor(BaseModel):
    """An evaluator: a judge or decision model whose verdicts are recorded as feedback.

    Evaluators only give feedback; every other command from one is forbidden.
    """

    model_config = ConfigDict(frozen=True)

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
        """How this actor is named in change notes."""
        return f"{self.name}@{self.version}"


Actor = Annotated[
    UserActor | AgentActor | ExternalAgentActor | SystemActor | EvaluatorActor,
    Field(discriminator="kind"),
]
"""Any actor, discriminated by ``kind``."""


def is_agent(actor: Actor) -> bool:
    """Return whether the actor is an agent, built-in or external.

    Agents are subject to artifact write policies; people and the system are not.
    """
    return isinstance(actor, AgentActor | ExternalAgentActor)


def same_participant(a: Actor, b: Actor) -> bool:
    """Return whether two actors are the same participant."""
    return a.participant == b.participant
