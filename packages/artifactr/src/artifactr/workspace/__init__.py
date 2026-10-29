"""Tenant-scoped workspaces over pluggable storage.

Open a :class:`Workspace` with :meth:`Workspaces.open`; every read and write goes through it,
each asks the application's ``authorize`` hook, every read leaves out what its ``hidden``
hook hides, every command passes the application's ``checks``, and every write runs core's rules
in one storage transaction.
"""

from artifactr.workspace.gate import KeyOf, integration_gate
from artifactr.workspace.memory import InMemoryStorage
from artifactr.workspace.storage import HistoryChunk, Scope, Storage, Transaction, dated, seal
from artifactr.workspace.workspace import (
    ACTIONS,
    MAX_COUNT,
    Access,
    ArtifactBusy,
    ArtifactLease,
    Authorize,
    Changes,
    Check,
    DirectWrites,
    Gate,
    Hidden,
    OnOpen,
    ThreadBusy,
    Workspace,
    Workspaces,
)
from artifactr.workspace.writes import DIRECT_WRITES, direct_writes, direct_writes_from

__all__ = [
    "ACTIONS",
    "DIRECT_WRITES",
    "MAX_COUNT",
    "Access",
    "ArtifactBusy",
    "ArtifactLease",
    "Authorize",
    "Changes",
    "Check",
    "DirectWrites",
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
    "dated",
    "direct_writes",
    "direct_writes_from",
    "integration_gate",
    "seal",
]
