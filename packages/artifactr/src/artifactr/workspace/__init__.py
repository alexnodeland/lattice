"""Tenant-scoped workspaces over pluggable storage.

Open a :class:`Workspace` with :meth:`Workspaces.open`; every read and write goes through it,
and every write runs core's rules in one storage transaction.
"""

from artifactr.workspace.memory import InMemoryStorage
from artifactr.workspace.storage import Scope, Storage, Transaction
from artifactr.workspace.workspace import ThreadBusy, Workspace, Workspaces

__all__ = [
    "InMemoryStorage",
    "Scope",
    "Storage",
    "ThreadBusy",
    "Transaction",
    "Workspace",
    "Workspaces",
]
