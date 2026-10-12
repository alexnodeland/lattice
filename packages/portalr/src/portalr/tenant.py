"""The tenant a read is for, which only an allowed check makes.

Every reader takes a :class:`Tenant`, never a string from the request, so no read reaches a tool
before grantr has allowed it. portalr's router makes one after ``grants.check`` answers yes; a
reader can't be handed a tenant any other way.
"""

from typing import Final, final

_ALLOWED: Final = object()


@final
class Tenant:
    """A tenant whose read grantr allowed."""

    __slots__ = ("id",)
    id: str

    def __init__(self, tenant_id: str, *, allowed: object) -> None:
        if allowed is not _ALLOWED:
            raise TypeError("a Tenant is made only by allowed(), after grantr's check")
        self.id = tenant_id

    def __repr__(self) -> str:
        return f"Tenant({self.id!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Tenant) and other.id == self.id

    def __hash__(self) -> int:
        return hash(self.id)


def allowed(tenant_id: str) -> Tenant:
    """The tenant, for a read grantr has just allowed. Only portalr's router calls this."""
    return Tenant(tenant_id, allowed=_ALLOWED)
