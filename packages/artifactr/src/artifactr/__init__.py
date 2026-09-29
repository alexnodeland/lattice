"""Build chat applications where people and agents collaborate through shared artifacts.

The names most applications need are available here. Everything else lives in the layer
packages: :mod:`artifactr.core` (pure rules), :mod:`artifactr.workspace` (scoped handles and
storage), :mod:`artifactr.agent` (the pydantic-ai integration), and the optional adapters.
"""

from importlib.metadata import version

from artifactr.agent import ArtifactDraft, ArtifactWorkspace, RunHandle, Runner, Session
from artifactr.core import (
    Actor,
    AgentActor,
    Applied,
    Artifact,
    EvaluatorActor,
    ExternalAgentActor,
    Feedback,
    JsonPatch,
    MarkdownArtifact,
    NotFound,
    Proposed,
    Recorded,
    Rejection,
    Resolved,
    SystemActor,
    TextEdit,
    TextEdits,
    UserActor,
    VersionConflict,
    Versioned,
    WritePolicy,
    new_id,
)
from artifactr.workspace import InMemoryStorage, Workspace, Workspaces

__version__ = version("artifactr-ai")

__all__ = [
    "Actor",
    "AgentActor",
    "Applied",
    "Artifact",
    "ArtifactDraft",
    "ArtifactWorkspace",
    "EvaluatorActor",
    "ExternalAgentActor",
    "Feedback",
    "InMemoryStorage",
    "JsonPatch",
    "MarkdownArtifact",
    "NotFound",
    "Proposed",
    "Recorded",
    "Rejection",
    "Resolved",
    "RunHandle",
    "Runner",
    "Session",
    "SystemActor",
    "TextEdit",
    "TextEdits",
    "UserActor",
    "VersionConflict",
    "Versioned",
    "Workspace",
    "Workspaces",
    "WritePolicy",
    "__version__",
    "new_id",
]
