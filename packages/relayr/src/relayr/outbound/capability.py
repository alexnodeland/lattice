"""The ArtifactrCapability: a rule's agent acts in artifactr, through pydantic-ai tools.

Add it beside reflexr's `EventContext` to an agent whose `deps_type` is reflexr's `Reaction`. Its
tools are the [`RunActions`][relayr.outbound.RunActions] of the run's attempt, so an agent's
writes are made once however often the run is retried, as a function action's are. A tool the
rule's allowlist refuses (`NotAllowed`), or artifactr refuses as invalid or about something
missing (`Refused`), goes back to the model, which may retry; any other refusal fails the run.
"""

from dataclasses import dataclass, field
from typing import Any, override

from pydantic_ai import FunctionToolset
from pydantic_ai.capabilities import AbstractCapability

from reflexr.workspace import Reaction
from relayr.outbound.actions import Outbound
from relayr.outbound.tools import artifactr_tools

INSTRUCTIONS = (
    "You can act in the chat workspace, as this rule's own participant. Your changes to "
    "artifacts are proposals for people to review, unless your rule may make them directly. "
    "Post a notice to tell people something: it starts no conversation with the assistant."
)


@dataclass
class ArtifactrCapability(AbstractCapability[Reaction[Any]]):
    """Give a rule's agent tools to read and write artifacts, post notices, and more if allowed.

    Args:
        outbound: The adapter the tools act through.
    """

    outbound: Outbound
    _toolset: FunctionToolset[Reaction[Any]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._toolset = artifactr_tools(self.outbound)

    @override
    def get_toolset(self) -> FunctionToolset[Reaction[Any]]:
        """Return the tools for acting in artifactr."""
        return self._toolset

    @override
    def get_instructions(self) -> str:
        """Return the instructions: how the agent's writes reach people."""
        return INSTRUCTIONS
