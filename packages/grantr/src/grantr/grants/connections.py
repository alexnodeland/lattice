"""grantr's connections: the outside clients people connected to their tenants (grantr ADR-0043).

A person connects a client through portr's consent page (lattice RFC-0014): :meth:`connect` makes
the connection, one tenant each, with the toolsets the person chose and ``core`` always. portr
reads it on every call with :meth:`live`, so a revoked connection's next call is refused, and
notes the call with :meth:`used`.

Every member of a tenant holds ``grantr:read_connections`` and ``grantr:revoke_connection``, for
their own connections; whoever holds ``grantr:add_member`` on the tenant, its owners and admins,
reads and revokes every one. Each change is in the tenant's audit log, in its transaction.
"""

from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Final

from grantr.core import (
    TENANT,
    TENANT_ID,
    AuditEntry,
    ClientInfo,
    Connection,
    ConnectionMade,
    ConnectionRevoked,
    ConnectionToolsetsAdded,
    Forbidden,
    Invalid,
    Resource,
    Subject,
    TenantId,
    User,
    UserId,
    connection_id,
)
from grantr.core.roles import READ_CONNECTIONS, REVOKE_CONNECTION
from grantr.grants.calls import Change, Record
from grantr.grants.storage import Reads, Storage, Transaction
from lattice_core.commands import Toolset

type Require = Callable[[Reads, TenantId, Subject, str, Resource], Awaitable[None]]
"""Refuses a subject that doesn't hold an action on a resource, from :class:`Grants`."""

type Held = Callable[[Reads, TenantId, Subject, Resource], Awaitable[frozenset[str]]]
"""The actions a subject holds on a resource, from :class:`Grants`."""

MANAGE_MEMBERS: Final = "grantr:add_member"
"""What reading and revoking another member's connections asks, beside the connections' own
actions: whoever adds the tenant's members manages what they connected."""

USED_EVERY: Final = timedelta(minutes=5)
"""How far behind a connection's ``last_used_at`` may be: :meth:`GrantrConnections.used` writes
at most this often."""


class GrantrConnections:
    """The connections over grantr's storage, and the commands that change them.

    What :meth:`Grants.connections` returns.

    Args:
        storage: grantr's storage.
        change: A change to one tenant, from :class:`~grantr.grants.Grants`.
        require: Refuses a subject that doesn't hold an action, from
            :class:`~grantr.grants.Grants`.
        held: The actions a subject holds, from :class:`~grantr.grants.Grants`.
        clock: The time :meth:`used` notes; the system's, in UTC, if omitted.
    """

    def __init__(
        self,
        storage: Storage,
        *,
        change: Change,
        require: Require,
        held: Held,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._storage = storage
        self._change = change
        self._require = require
        self._held = held
        self._clock = clock or (lambda: datetime.now(UTC))

    async def connect(
        self,
        tenant: TenantId,
        client: ClientInfo,
        *,
        toolsets: Iterable[Toolset] = (),
        by: User,
    ) -> Connection:
        """Connect a client to the tenant for the person ``by``, and return the connection.

        A person connects only themselves. Where they already have a live connection of the
        client in the tenant, it is that one, with the toolsets added, as a client that steps up
        to a toolset is sent back to the consent page.

        Raises:
            Invalid: If the tenant's id can't be one.
            Forbidden: If ``by`` isn't a member of the tenant: they don't hold
                ``grantr:read_connections`` on it.
        """
        if not TENANT_ID.fullmatch(tenant):
            raise Invalid("a tenant's id isn't empty, and has no ~")
        async with self._change(tenant) as (tx, record):
            await self._require(tx, tenant, by, READ_CONNECTIONS, TENANT)
            existing = _live(await tx.connections(tenant, user=by.id, client=client.client_id))
            if existing is not None:
                return await self._add(tx, record, existing, frozenset(toolsets), by)
            made = Connection(
                id=connection_id(),
                tenant=tenant,
                user=by,
                client=client,
                toolsets=frozenset(toolsets),
                created_at=self._clock(),
            )
            event = ConnectionMade(
                connection=made.id,
                user=by.id,
                client=client.client_id,
                name=client.name,
                toolsets=sorted(made.toolsets),
            )
            entry = await record(tenant, by, event)
            made = made.model_copy(update={"created_at": entry.at})
            await tx.put_connection(made)
            return made

    async def add_toolsets(
        self, tenant: TenantId, id: str, toolsets: Iterable[Toolset], /, *, by: User
    ) -> Connection:
        """Let one of ``by``'s own live connections use more toolsets, and return it.

        Raises:
            Invalid: If the tenant has no live connection of the id that is ``by``'s.
            Forbidden: If ``by`` isn't a member of the tenant.
        """
        async with self._change(tenant) as (tx, record):
            await self._require(tx, tenant, by, READ_CONNECTIONS, TENANT)
            found = await tx.connection(tenant, id)
            if found is None or not found.live or found.user != by:
                raise Invalid(f"you have no live connection {id}")
            return await self._add(tx, record, found, frozenset(toolsets), by)

    async def _add(
        self,
        tx: Transaction,
        record: Record,
        connection: Connection,
        toolsets: frozenset[Toolset],
        by: User,
    ) -> Connection:
        if toolsets <= connection.toolsets:
            return connection
        grown = connection.model_copy(update={"toolsets": connection.toolsets | toolsets})
        event = ConnectionToolsetsAdded(
            connection=grown.id, user=by.id, toolsets=sorted(grown.toolsets)
        )
        await record(connection.tenant, by, event)
        await tx.put_connection(grown)
        return grown

    async def listed(
        self, tenant: TenantId, *, by: Subject, user: UserId | None = None
    ) -> list[Connection]:
        """The tenant's connections ``by`` may read, revoked ones too, oldest first.

        A member reads their own; whoever holds ``grantr:add_member`` on the tenant, every one,
        or one person's with ``user``.

        Raises:
            Forbidden: If ``by`` doesn't hold ``grantr:read_connections`` on the tenant, or
                names another person without ``grantr:add_member``.
        """
        await self._require(self._storage, tenant, by, READ_CONNECTIONS, TENANT)
        if MANAGE_MEMBERS in await self._held(self._storage, tenant, by, TENANT):
            return await self._storage.connections(tenant, user=user)
        own = by.id if isinstance(by, User) else None
        if user is not None and user != own:
            raise Forbidden(f"{MANAGE_MEMBERS} on the tenant is refused")
        return [] if own is None else await self._storage.connections(tenant, user=own)

    async def revoke(
        self, tenant: TenantId, id: str, /, *, by: Subject, own_only: bool = False
    ) -> AuditEntry:
        """Revoke one of the tenant's connections, and return the entry.

        Its next call is refused, since every call reads the connection.

        Args:
            tenant: The connection's tenant.
            id: The connection's id.
            by: Who revokes it.
            own_only: Refuse a connection that isn't ``by``'s, as ``grantr.revoke_connection``
                does; revoking another's is ``grantr.revoke_member_connection``, which asks its
                caller's confirmation (lattice RFC-0014).

        Raises:
            Invalid: If the tenant has no connection of the id, or it is revoked already.
            Forbidden: If ``by`` doesn't hold ``grantr:revoke_connection`` on the tenant, or the
                connection is another's and ``own_only`` or ``by`` doesn't hold
                ``grantr:add_member`` there.
        """
        async with self._change(tenant) as (tx, record):
            await self._require(tx, tenant, by, REVOKE_CONNECTION, TENANT)
            found = await tx.connection(tenant, id)
            if found is None:
                raise Invalid(f"there is no connection {id}")
            if found.user != by:
                if own_only:
                    raise Forbidden(f"{id} isn't yours: revoking another's is its own command")
                await self._require(tx, tenant, by, MANAGE_MEMBERS, TENANT)
            if not found.live:
                raise Invalid(f"{id} is revoked already")
            event = ConnectionRevoked(
                connection=id,
                user=found.user.id,
                client=found.client.client_id,
                name=found.client.name,
            )
            entry = await record(tenant, by, event)
            await tx.put_connection(found.model_copy(update={"revoked_at": entry.at}))
            return entry

    async def live(self, tenant: TenantId, client_id: str, user: UserId) -> Connection | None:
        """The person's live connection of the client in the tenant, or None: portr's check.

        An id no tenant can have has none.
        """
        if not TENANT_ID.fullmatch(tenant):
            return None
        return _live(await self._storage.connections(tenant, user=user, client=client_id))

    async def used(self, connection: Connection, /) -> None:
        """Note that a live connection was used, at most every :data:`USED_EVERY`.

        It isn't audited: the calls themselves are, each a ``capability_called`` entry.
        """
        now = self._clock()
        last = connection.last_used_at
        if not connection.live or (last is not None and now - last < USED_EVERY):
            return
        async with self._storage.transaction(connection.tenant) as tx:
            current = await tx.connection(connection.tenant, connection.id)
            if current is not None and current.live:
                await tx.put_connection(current.model_copy(update={"last_used_at": now}))


def _live(connections: list[Connection]) -> Connection | None:
    """The newest live connection of those, or None."""
    return next((c for c in reversed(connections) if c.live), None)
