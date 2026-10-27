"""portalr's router, which an application mounts at ``/portalr``, and its settings.

With mini apps, :class:`SandboxOrigin` serves their sandbox on an origin of its own. A portal
reached at several origins names a :class:`Place` beside each, which :func:`beside` derives
(portalr ADR-0083).
"""

from portalr.fastapi.router import UI, Config, Invited, Links, NewInvite, portalr_router
from portalr.fastapi.sandbox import SandboxOrigin
from portalr.fastapi.site import Place, Site, Surfaces, beside

__all__ = [
    "UI",
    "Config",
    "Invited",
    "Links",
    "NewInvite",
    "Place",
    "SandboxOrigin",
    "Site",
    "Surfaces",
    "beside",
    "portalr_router",
]
