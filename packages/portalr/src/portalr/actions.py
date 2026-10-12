"""portalr's catalog: the actions its routes check, which the application hands grantr.

A tenant's ``owner`` and ``admin`` hold the tenant's reads, and the deployment's ``operator``
holds the read across tenants (lattice RFC-0002).
"""

from typing import Final

READ_TELEMETRY: Final = "portalr:read_telemetry"
"""Read a tenant's feedback, scores, traces, logs and metrics."""

READ_SPEND: Final = "portalr:read_spend"
"""Read a tenant's usage and spend."""

READ_DEPLOYMENT: Final = "portalr:read_deployment"
"""Read across tenants: every tenant's spend, and deep links into the stack's own tools."""

ACTIONS: Final = frozenset({READ_TELEMETRY, READ_SPEND, READ_DEPLOYMENT})
"""Every action portalr checks, for ``Grants(catalogs=...)``."""
