"""An application's Integrations, as a test switches them."""

from dataclasses import dataclass, field


@dataclass
class Toggles:
    """Integrations that are on unless a test switched them off, by workspace."""

    off: dict[str, set[str]] = field(default_factory=dict[str, set[str]])
    asked: list[tuple[str, str, str]] = field(default_factory=list[tuple[str, str, str]])

    async def is_enabled(self, tenant_id: str, workspace_id: str, key: str) -> bool:
        self.asked.append((tenant_id, workspace_id, key))
        return key not in self.off.get(workspace_id, set())
