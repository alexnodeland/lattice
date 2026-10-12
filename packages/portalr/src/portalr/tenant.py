"""The tenant a read is for, which only an allowed check makes.

Every reader takes a :class:`Tenant`, never a string from the request. portalr's router makes one
with :func:`allowed` after ``grants.check`` answers yes. Python can't keep other code from calling
:func:`allowed`; what keeps it to the router is the layering test, which fails if any other
module imports it. A ``Tenant``, once made, can't be changed.
"""

from typing import Final, final

_ALLOWED: Final = object()


@final
class Tenant:
    """A tenant whose read grantr allowed, by its id; read-only."""

    __slots__ = ("_id",)
    _id: str

    def __init__(self, tenant_id: str, *, allowed: object) -> None:
        if allowed is not _ALLOWED:
            raise TypeError("a Tenant is made only by allowed(), after grantr's check")
        object.__setattr__(self, "_id", tenant_id)

    @property
    def id(self) -> str:
        """The tenant's id, as grantr names it."""
        return self._id

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("a Tenant can't be changed")

    def __repr__(self) -> str:
        return f"Tenant({self._id!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Tenant) and other.id == self._id

    def __hash__(self) -> int:
        return hash(self._id)


def allowed(tenant_id: str) -> Tenant:
    """The tenant, for a read grantr has just allowed. Only portalr's router calls this."""
    return Tenant(tenant_id, allowed=_ALLOWED)
