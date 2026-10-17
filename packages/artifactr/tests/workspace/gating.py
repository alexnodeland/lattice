"""An integration switch for tests of the gate (ADR-0081): notes are the ``notes`` integration's."""

from collections.abc import Mapping

from pydantic import JsonValue

from artifactr.core import TenantId, WorkspaceId

NOTES = "notes"


class Switch:
    """An ``Integrations`` that is on unless a tenant's workspace has a key switched off."""

    def __init__(self) -> None:
        self.off: set[tuple[TenantId, WorkspaceId, str]] = set()
        self.calls: list[str] = []
        """What it was asked, in order, with whatever a test records beside it."""

    async def is_enabled(self, tenant_id: str, workspace_id: str, key: str, /) -> bool:
        self.calls.append(f"is_enabled {key}")
        return (tenant_id, workspace_id, key) not in self.off


def key_of(kind: str, data: Mapping[str, JsonValue]) -> str | None:
    """Notes are the ``notes`` integration's; nothing else is any integration's."""
    return NOTES if kind == "note" else None
