"""portalr's actions held as lattice RFC-0002 intends, over grantr's own checks.

grantr's built-in roles don't yet place portalr's catalog: its ``read_`` prefix rule puts every
portalr read in ``viewer``, and ``operator`` holds none. Until grantr's roles change, the router's
tests answer portalr's actions here, from grantr's memberships and operators, and pass every other
check to grantr.
"""

from grantr.core import DEPLOYMENT, AuditEntry, Member, Resource, Subject, TenantId, User
from grantr.grants import Grants
from portalr.actions import READ_DEPLOYMENT, READ_SPEND, READ_TELEMETRY


class Intended:
    """grantr's ``Grants``, with portalr's actions held as the RFC intends."""

    def __init__(self, grants: Grants) -> None:
        self.grants = grants

    async def check(self, tenant: TenantId, subject: Subject, action: str, on: Resource) -> bool:
        if action == READ_DEPLOYMENT:
            # The operator role holds it; grantr's operators are those who can list tenants.
            return await self.grants.check(tenant, subject, "grantr:create_tenant", DEPLOYMENT)
        if action in (READ_TELEMETRY, READ_SPEND):
            if not isinstance(subject, User):
                return False
            return bool({"owner", "admin"} & set(await self.grants.tenant_roles(tenant, subject)))
        return await self.grants.check(tenant, subject, action, on)

    async def add_member(self, tenant: TenantId, member: Member, *, by: Subject) -> AuditEntry:
        return await self.grants.add_member(tenant, member, by=by)

    async def tenants(self, *, by: Subject) -> list[TenantId]:
        return await self.grants.tenants(by=by)
