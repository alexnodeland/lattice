"""Tenant-scoped workspaces over pluggable storage.

Open a :class:`Workspace` with :meth:`Workspaces.open`; every read and write goes through it,
each asks the application's ``authorize`` hook, and every write runs core's rules in one
storage transaction.
"""

from artifactr.workspace.memory import InMemoryStorage
from artifactr.workspace.storage import HistoryChunk, Scope, Storage, Transaction, seal
from artifactr.workspace.workspace import (
    ACTIONS,
    MAX_COUNT,
    Access,
    Authorize,
    OnOpen,
    ThreadBusy,
    Workspace,
    Workspaces,
)

__all__ = [
    "ACTIONS",
    "MAX_COUNT",
    "Access",
    "Authorize",
    "HistoryChunk",
    "InMemoryStorage",
    "OnOpen",
    "Scope",
    "Storage",
    "ThreadBusy",
    "Transaction",
    "Workspace",
    "Workspaces",
    "seal",
]
