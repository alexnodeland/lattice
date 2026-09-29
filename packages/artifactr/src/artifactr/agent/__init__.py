"""artifactr's integration with pydantic-ai.

Give an agent the :class:`ArtifactWorkspace` capability and ``deps_type=Session[...]``, then run
it in threads with a :class:`Runner`::

    agent = Agent(
        "anthropic:claude-sonnet-5-5",
        deps_type=Session[None],
        capabilities=[ArtifactWorkspace(types=[Doc, Plan])],
    )
    runner = Runner(agent, app=None)
    await runner.send(workspace, thread_id, "Draft a launch plan")
"""

from artifactr.agent.capability import ArtifactWorkspace, RunFailure
from artifactr.agent.live import (
    ArtifactDraft,
    FanoutChannel,
    LiveChannel,
    NullChannel,
    forward_live,
    to_live,
)
from artifactr.agent.runner import (
    EndedTurn,
    RunHandle,
    Runner,
    Sent,
    TurnContext,
    TurnEvaluator,
    TurnOutcome,
)
from artifactr.agent.session import Session, Trigger, last_seen, load_history
from artifactr.agent.tools import (
    artifact_text,
    artifact_tools,
    describe_outcome,
    list_artifacts_text,
    submit,
)

__all__ = [
    "ArtifactDraft",
    "ArtifactWorkspace",
    "EndedTurn",
    "FanoutChannel",
    "LiveChannel",
    "NullChannel",
    "RunFailure",
    "RunHandle",
    "Runner",
    "Sent",
    "Session",
    "Trigger",
    "TurnContext",
    "TurnEvaluator",
    "TurnOutcome",
    "artifact_text",
    "artifact_tools",
    "describe_outcome",
    "forward_live",
    "last_seen",
    "list_artifacts_text",
    "load_history",
    "submit",
    "to_live",
]
