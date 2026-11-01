"""grantr's connections over every storage (lattice RFC-0014, grantr ADR-0043).

A member connects a client to a tenant, with the toolsets they chose and ``core`` always; they
read and revoke their own, and whoever adds the tenant's members reads and revokes every one;
portr's check finds a person's live connection of a client, and a revoked one is gone from it.
"""

from datetime import timedelta

import pytest

from grantr.core import (
    TENANT,
    Agent,
    AuditFilter,
    ClientInfo,
    ConnectionMade,
    ConnectionRevoked,
    ConnectionToolsetsAdded,
    Forbidden,
    Invalid,
    ServicePrincipal,
    User,
)
from grantr.grants import Grants, Storage
from tests.catalogs import ARTIFACTR, PORTALR, REFLEXR
from tests.grants.conftest import ALICE, NOW, ROOT

BOB = User(id="bob")
"""acme's admin, who adds its members."""

CAROL = User(id="carol")
"""acme's member, who holds nothing more."""

DAVE = User(id="dave")
"""globex's owner, no member of acme."""

CI = ServicePrincipal(id="ci")
"""acme's service principal, a member."""

CLAUDE = ClientInfo(client_id="client_claude", name="Claude", uri="https://claude.ai")
CURSOR = ClientInfo(client_id="client_cursor", name="Cursor")
CONNECTIONS = AuditFilter(
    types=frozenset({"connection_made", "connection_toolsets_added", "connection_revoked"})
)


async def _grants(storage: Storage) -> Grants:
    grants = Grants(storage, catalogs=[ARTIFACTR, REFLEXR, PORTALR])
    await grants.first_operator(ROOT.id)
    await grants.create_tenant("acme", owner=ALICE.id, by=ROOT)
    for member in (BOB, CAROL, CI):
        await grants.add_member("acme", member, by=ALICE)
    await grants.grant("acme", "admin", on=TENANT, to=BOB, by=ALICE)
    await grants.create_tenant("globex", owner=DAVE.id, by=ROOT)
    return grants


async def test_a_member_connects_a_client_and_it_is_audited(storage: Storage) -> None:
    grants = await _grants(storage)
    connections = grants.connections()
    made = await connections.connect("acme", CLAUDE, toolsets=["files"], by=CAROL)
    assert made.id.startswith("con_")
    assert (made.tenant, made.user, made.client) == ("acme", CAROL, CLAUDE)
    assert made.toolsets == {"core", "files"}
    assert (made.last_used_at, made.revoked_at, made.live) == (None, None, True)
    [entry] = await grants.audit("acme", by=ALICE, keep=CONNECTIONS)
    assert entry.by == CAROL
    assert entry.at == made.created_at
    assert entry.event == ConnectionMade(
        connection=made.id,
        user="carol",
        client="client_claude",
        name="Claude",
        toolsets=["core", "files"],
    )
    assert await connections.live("acme", "client_claude", "carol") == made


async def test_connecting_a_client_again_adds_to_its_live_connection(storage: Storage) -> None:
    grants = await _grants(storage)
    connections = grants.connections()
    made = await connections.connect("acme", CLAUDE, by=CAROL)
    assert made.toolsets == {"core"}
    again = await connections.connect("acme", CLAUDE, toolsets=["core"], by=CAROL)
    assert again == made, "nothing new: the same connection, unaudited"
    grown = await connections.connect("acme", CLAUDE, toolsets=["automations"], by=CAROL)
    assert (grown.id, grown.toolsets) == (made.id, {"core", "automations"})
    stepped = await connections.add_toolsets("acme", made.id, ["research"], by=CAROL)
    assert stepped.toolsets == {"core", "automations", "research"}
    types = [e.event for e in await grants.audit("acme", by=ALICE, keep=CONNECTIONS)]
    assert types[1:] == [
        ConnectionToolsetsAdded(connection=made.id, user="carol", toolsets=["automations", "core"]),
        ConnectionToolsetsAdded(
            connection=made.id, user="carol", toolsets=["automations", "core", "research"]
        ),
    ]
    other = await connections.connect("acme", CURSOR, by=CAROL)
    assert other.id != made.id, "another client is another connection"


async def test_only_a_member_connects_and_only_their_own(storage: Storage) -> None:
    grants = await _grants(storage)
    connections = grants.connections()
    with pytest.raises(Forbidden, match="grantr:read_connections"):
        await connections.connect("acme", CLAUDE, by=DAVE)
    with pytest.raises(Invalid, match="a tenant's id"):
        await connections.connect("ac~me", CLAUDE, by=CAROL)
    made = await connections.connect("acme", CLAUDE, by=CAROL)
    with pytest.raises(Invalid, match="you have no live connection"):
        await connections.add_toolsets("acme", made.id, ["files"], by=BOB)
    with pytest.raises(Invalid, match="you have no live connection"):
        await connections.add_toolsets("acme", "con_" + "0" * 16, ["files"], by=CAROL)
    assert await connections.live("globex", "client_claude", "carol") is None
    assert await connections.live("ac~me", "client_claude", "carol") is None


async def test_a_member_reads_their_own_and_an_admin_every_one(storage: Storage) -> None:
    grants = await _grants(storage)
    connections = grants.connections()
    carols = await connections.connect("acme", CLAUDE, by=CAROL)
    alices = await connections.connect("acme", CURSOR, by=ALICE)
    assert await connections.listed("acme", by=CAROL) == [carols]
    assert await connections.listed("acme", by=CAROL, user="carol") == [carols]
    with pytest.raises(Forbidden, match="grantr:add_member"):
        await connections.listed("acme", by=CAROL, user="alice")
    every = await connections.listed("acme", by=BOB)
    assert sorted(every, key=lambda c: c.user.id) == [alices, carols], "made at the same time"
    assert await storage.connection("acme", carols.id) == carols
    assert await storage.connection("acme", "con_" + "0" * 16) is None
    assert await connections.listed("acme", by=BOB, user="alice") == [alices]
    assert await connections.listed("acme", by=CI) == [], "a service principal connects none"
    with pytest.raises(Forbidden):
        await connections.listed("acme", by=DAVE)
    with pytest.raises(Forbidden):
        await connections.listed("acme", by=Agent())


async def test_revoking_a_connection_ends_it(storage: Storage) -> None:
    grants = await _grants(storage)
    connections = grants.connections()
    made = await connections.connect("acme", CLAUDE, by=CAROL)
    entry = await connections.revoke("acme", made.id, by=CAROL, own_only=True)
    assert entry.event == ConnectionRevoked(
        connection=made.id, user="carol", client="client_claude", name="Claude"
    )
    assert await connections.live("acme", "client_claude", "carol") is None
    [revoked] = await connections.listed("acme", by=CAROL)
    assert (revoked.live, revoked.revoked_at) == (False, entry.at)
    with pytest.raises(Invalid, match="revoked already"):
        await connections.revoke("acme", made.id, by=CAROL)
    with pytest.raises(Invalid, match="there is no connection"):
        await connections.revoke("acme", "con_" + "0" * 16, by=CAROL)
    with pytest.raises(Invalid, match="you have no live connection"):
        await connections.add_toolsets("acme", made.id, ["files"], by=CAROL)
    fresh = await connections.connect("acme", CLAUDE, by=CAROL)
    assert fresh.id != made.id, "connecting again after a revocation is a new connection"


async def test_another_members_connection_is_revoked_by_an_admin_alone(storage: Storage) -> None:
    grants = await _grants(storage)
    connections = grants.connections()
    alices = await connections.connect("acme", CLAUDE, by=ALICE)
    with pytest.raises(Forbidden, match="grantr:add_member"):
        await connections.revoke("acme", alices.id, by=CAROL)
    with pytest.raises(Forbidden, match="isn't yours"):
        await connections.revoke("acme", alices.id, by=BOB, own_only=True)
    entry = await connections.revoke("acme", alices.id, by=BOB)
    assert entry.by == BOB
    with pytest.raises(Forbidden):
        await connections.revoke("acme", alices.id, by=DAVE)


async def test_a_use_is_noted_every_few_minutes(storage: Storage) -> None:
    grants = await _grants(storage)
    now = [NOW]
    connections = grants.connections(clock=lambda: now[0])
    made = await connections.connect("acme", CLAUDE, by=CAROL)
    await connections.used(made)
    noted = await connections.live("acme", "client_claude", "carol")
    assert noted is not None
    assert noted.last_used_at == NOW
    now[0] = NOW + timedelta(minutes=4)
    await connections.used(noted)
    same = await connections.live("acme", "client_claude", "carol")
    assert same is not None
    assert same.last_used_at == NOW, "within five minutes, not written"
    now[0] = NOW + timedelta(minutes=5)
    await connections.used(same)
    later = await connections.live("acme", "client_claude", "carol")
    assert later is not None
    assert later.last_used_at == now[0]
    await connections.revoke("acme", made.id, by=CAROL)
    now[0] = NOW + timedelta(hours=1)
    await connections.used(later)  # read before its revocation: it is revoked now
    [revoked] = await connections.listed("acme", by=CAROL)
    assert revoked.last_used_at == NOW + timedelta(minutes=5)
    await connections.used(revoked)
    assert (await connections.listed("acme", by=CAROL))[0].last_used_at == revoked.last_used_at


async def test_a_members_connections_go_with_them_and_the_tenants_with_it(
    storage: Storage,
) -> None:
    grants = await _grants(storage)
    connections = grants.connections()
    await connections.connect("acme", CLAUDE, by=CAROL)
    await connections.connect("acme", CLAUDE, by=ALICE)
    await grants.remove_member("acme", CAROL, by=ALICE)
    assert [c.user for c in await connections.listed("acme", by=ALICE)] == [ALICE]
    await grants.remove_member("acme", CI, by=ALICE)
    await grants.delete_tenant("acme", by=ALICE)
    await grants.create_tenant("acme", owner=ALICE.id, by=ROOT)
    assert await connections.listed("acme", by=ALICE) == []
