"""Build chat applications where people and agents collaborate through shared artifacts.

The names most applications need are available here. Everything else lives in the layer
packages: :mod:`artifactr.core` (pure rules), :mod:`artifactr.workspace` (scoped handles and
storage), and the optional adapters.
"""

from importlib.metadata import version

from artifactr.core import (
    Actor,
    AgentActor,
    Applied,
    Artifact,
    ExternalAgentActor,
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

__version__ = version("artifactr")

__all__ = [
    "Actor",
    "AgentActor",
    "Applied",
    "Artifact",
    "ExternalAgentActor",
    "InMemoryStorage",
    "JsonPatch",
    "MarkdownArtifact",
    "NotFound",
    "Proposed",
    "Recorded",
    "Rejection",
    "Resolved",
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
