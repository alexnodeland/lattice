"""Whether an integration runs in a workspace: the seam relayr's integrations consult first.

An integration is named by a key, such as `tracker:plane` or `tracker:vikunja`. Before it acts in
a workspace, it asks an [`Enabled`][relayr.integrations.Enabled]; one that says no writes nothing,
reads nothing and keeps nothing. Where the answer comes from (a store of switches per deployment,
tenant and workspace, audited, and an admin page that sets them) is the application's to give.
Without one, every integration runs: [`always`][relayr.integrations.always].
"""

from typing import Protocol

__all__ = ["Enabled", "always"]


class Enabled(Protocol):
    """Answers whether an integration runs in a tenant's workspace."""

    async def __call__(self, tenant_id: str, workspace_id: str, key: str, /) -> bool:
        """Return whether the integration `key` runs in the workspace."""
        ...


async def always(_tenant_id: str, _workspace_id: str, _key: str, /) -> bool:
    """Every integration runs everywhere: the answer when the application gives none."""
    return True
