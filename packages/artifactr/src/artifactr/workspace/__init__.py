"""Tenant-scoped workspaces over pluggable storage.

Open a :class:`Workspace` with :meth:`Workspaces.open`; every read and write goes through it,
each asks the application's ``authorize`` hook, every read leaves out what its ``hidden``
hook hides, and every write runs core's rules in one
storage transaction.
"""

from artifactr.workspace.gate import KeyOf, integration_gate
from artifactr.workspace.memory import InMemoryStorage
from artifactr.workspace.storage import HistoryChunk, Scope, Storage, Transaction, seal
from artifactr.workspace.workspace import (
    ACTIONS,
    MAX_COUNT,
    Access,
    ArtifactBusy,
    ArtifactLease,
    Authorize,
    Gate,
    Hidden,
    OnOpen,
    ThreadBusy,
    Workspace,
    Workspaces,
)

__all__ = [
    "ACTIONS",
    "MAX_COUNT",
    "Access",
    "ArtifactBusy",
    "ArtifactLease",
    "Authorize",
    "Gate",
    "Hidden",
    "HistoryChunk",
    "InMemoryStorage",
    "KeyOf",
    "OnOpen",
    "Scope",
    "Storage",
    "ThreadBusy",
    "Transaction",
    "Workspace",
    "Workspaces",
    "integration_gate",
    "seal",
]
