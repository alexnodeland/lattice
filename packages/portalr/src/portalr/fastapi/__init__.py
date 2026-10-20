"""portalr's router, which an application mounts at ``/portalr``, and its settings.

With mini apps, :class:`SandboxOrigin` serves their sandbox on an origin of its own.
"""

from portalr.fastapi.router import UI, Config, Invited, Links, NewInvite, portalr_router
from portalr.fastapi.sandbox import SandboxOrigin
from portalr.fastapi.site import Site, Surfaces

__all__ = [
    "UI",
    "Config",
    "Invited",
    "Links",
    "NewInvite",
    "SandboxOrigin",
    "Site",
    "Surfaces",
    "portalr_router",
]
