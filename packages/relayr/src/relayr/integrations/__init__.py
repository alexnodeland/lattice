"""Whether an integration runs in a workspace: lattice-core's port, answered without a store.

An integration is named by a key, such as `tracker:plane` or `tracker:vikunja`. Before it acts in
a workspace, it asks lattice-core's `Integrations` port; one that says no writes nothing, reads
nothing and keeps nothing. grantr's `Grants` answers it from a store of switches per deployment,
tenant and workspace (lattice ADR-0027). Without one, every integration runs:
[`ALWAYS`][relayr.integrations.ALWAYS].
"""

from typing import Final

from lattice_core.integrations import Integrations

__all__ = ["ALWAYS"]


class _Always:
    """Every integration runs everywhere."""

    async def is_enabled(self, _tenant_id: str, _workspace_id: str | None, _key: str, /) -> bool:
        """Return True: the integration runs."""
        return True


ALWAYS: Final[Integrations] = _Always()
"""Every integration runs everywhere, a tracker's key lattice-core doesn't declare included: the
answer when the application gives no store."""
