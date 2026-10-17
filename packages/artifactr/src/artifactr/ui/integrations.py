"""Which of the forms layer's integrations are on in a workspace (ADR-0080).

An application injects an :class:`Integrations`, the port lattice's shared store of
integrations implements once it exists, designed apart from artifactr.ui. The port is generic,
a key per integration, so it moves to that shared home unchanged. artifactr.ui's keys are
:data:`FORMS`, :data:`DASHBOARDS` and :data:`MINI_APPS`; with none injected, forms and
dashboards are on and mini apps, RFC-0005's second phase, off.
"""

from typing import Final, Literal, Protocol

from artifactr.core import TenantId, WorkspaceId

__all__ = [
    "DASHBOARDS",
    "DEFAULT_ON",
    "FORMS",
    "MINI_APPS",
    "IntegrationKey",
    "Integrations",
    "is_enabled",
]

FORMS: Final = "ui:forms"
"""Forms: ``ask_form``, ``create_form``, and the submissions and answers people send."""

DASHBOARDS: Final = "ui:dashboards"
"""Dashboards: ``show_dashboard`` and ``update_dashboard``, and the dashboards they write."""

MINI_APPS: Final = "ui:mini-apps"
"""Mini apps, RFC-0005's second phase: off unless switched on. Nothing offers one yet."""

IntegrationKey = Literal["ui:forms", "ui:dashboards", "ui:mini-apps"]
"""The keys of forms, dashboards and mini apps."""

DEFAULT_ON: Final = frozenset({FORMS, DASHBOARDS})
"""The keys that are on when an application injects no :class:`Integrations`."""


class Integrations(Protocol):
    """Whether an integration is on in a workspace.

    The application's port, which lattice's shared store of integrations, by deployment, tenant
    and workspace, will implement. It is asked before each model request and each command of an
    integration's, so an implementation caches what it reads.
    """

    async def is_enabled(self, tenant_id: TenantId, workspace_id: WorkspaceId, key: str) -> bool:
        """Return whether the integration ``key`` is on in the tenant's workspace."""
        ...


async def is_enabled(
    integrations: Integrations | None,
    tenant_id: TenantId,
    workspace_id: WorkspaceId,
    key: IntegrationKey,
) -> bool:
    """Ask ``integrations``, or, without one, whether ``key`` is on by default."""
    if integrations is None:
        return key in DEFAULT_ON
    return await integrations.is_enabled(tenant_id, workspace_id, key)
