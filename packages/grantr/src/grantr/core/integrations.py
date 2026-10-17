"""Integrations, switched: how three levels decide whether one is on in a workspace.

The deployment installs some integrations, in its configuration: that is a ceiling. A tenant's
admins and a workspace's admins each turn an integration on or off, or leave it unset. An
integration is on in a workspace only if the deployment installs it and the tenant hasn't turned
it off; then the workspace's setting decides, or, unset, the tenant's, or, unset too, the
integration's default (grantr ADR-0034).
"""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict

from grantr.core.subjects import Subject


def effective(
    *, installed: bool, default: bool, tenant: bool | None, workspace: bool | None
) -> bool:
    """Whether an integration is on in a workspace.

    Args:
        installed: Whether the deployment installs it.
        default: Whether it is on where neither the tenant nor the workspace set it.
        tenant: The tenant's setting; None if unset.
        workspace: The workspace's setting; None if unset.
    """
    if not installed or tenant is False:
        return False
    if workspace is not None:
        return workspace
    return default if tenant is None else tenant


class IntegrationSetting(BaseModel):
    """One level's explicit setting of an integration: on or off, who set it, and when."""

    model_config = ConfigDict(frozen=True)

    on: bool
    by: Subject
    at: datetime
    """When it was set: its audit entry's time."""


class IntegrationState(BaseModel):
    """An integration as an admin reads it: what it is, each level's setting, and the outcome."""

    model_config = ConfigDict(frozen=True)

    key: str
    description: str
    default: bool
    installed: bool
    """Whether the deployment installs it: if not, it is off everywhere."""

    tenant: IntegrationSetting | None
    """The tenant's setting; None if unset."""

    workspace: IntegrationSetting | None
    """The workspace's setting; None if unset, and on the tenant."""

    enabled: bool
    """Whether it is on in the workspace; on the tenant, in a workspace that sets nothing."""

    @classmethod
    def of(
        cls,
        key: str,
        *,
        description: str,
        default: bool,
        installed: bool,
        tenant: IntegrationSetting | None,
        workspace: IntegrationSetting | None = None,
    ) -> Self:
        """The state of an integration, with whether it is on worked out from its levels."""
        return cls(
            key=key,
            description=description,
            default=default,
            installed=installed,
            tenant=tenant,
            workspace=workspace,
            enabled=effective(
                installed=installed,
                default=default,
                tenant=None if tenant is None else tenant.on,
                workspace=None if workspace is None else workspace.on,
            ),
        )
