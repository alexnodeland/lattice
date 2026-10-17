"""The TrackerCapability: a rule's agent files and changes items in its workspace's tracker.

Add it beside reflexr's `EventContext` to an agent whose `deps_type` is reflexr's `Reaction`.
Its tools are the [`TrackerActions`][relayr.trackers.TrackerActions] of the run's attempt, so an
agent's writes are made once however often the run is retried, as a function action's are. What
the rule's allowlist refuses (`NotAllowed`), or the tracker refuses as invalid or missing
(`TrackerRefused`), goes back to the model, which may retry; any other failure fails the run.
"""

from dataclasses import dataclass, field
from typing import Any, override

from pydantic_ai import FunctionToolset
from pydantic_ai.capabilities import AbstractCapability

from reflexr.workspace import Reaction
from relayr.trackers.actions import Trackers
from relayr.trackers.tools import tracker_tools

INSTRUCTIONS = (
    "You can file items in the team's task tracker, comment on them and move them between "
    "states. Name each item by a key that says what it is about, such as 'incident/<id>': "
    "filing by a key used before finds that item rather than filing another."
)


@dataclass
class TrackerCapability(AbstractCapability[Reaction[Any]]):
    """Give a rule's agent tools to file, comment on, move and read items in its tracker.

    Args:
        trackers: The connector the tools write through.
    """

    trackers: Trackers
    _toolset: FunctionToolset[Reaction[Any]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._toolset = tracker_tools(self.trackers)

    @override
    def get_toolset(self) -> FunctionToolset[Reaction[Any]]:
        """Return the tools for writing to the tracker."""
        return self._toolset

    @override
    def get_instructions(self) -> str:
        """Return the instructions: how the agent names the items it files."""
        return INSTRUCTIONS
