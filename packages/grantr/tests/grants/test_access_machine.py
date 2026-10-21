"""Access as a state machine: random commands in one tenant, against a model of what they may do.

Each step is a command made by a random subject: adding or removing a member, defining or
deleting a group, granting or revoking a role. The model predicts whether grantr carries it out
or refuses it, and with which error, in the order the command checks: the maker's own action
first (ADR-0010), then what the command names, then the bound (no one grants or revokes more
than they hold, ADR-0010, but for giving up one's own grant and an operator granting
themselves, ADR-0014), then the tenant's last owner (ADR-0014, as amended). After every step
the store holds the model's grants and groups, a member holds owner, and the tenant's audit log
replays to the same access (ADR-0007, ADR-0013); a check answers as the model holds, and writes
nothing (ADR-0015).

The model resolves groups, and the resources around a resource, itself; it reads only what
each built-in role holds from the catalog, as the specification's data.
"""

import asyncio
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass, field, replace
from typing import Any

import pytest
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from grantr.core import (
    TENANT,
    AuditEntry,
    Catalog,
    Forbidden,
    Grant,
    Granted,
    Grantee,
    Group,
    GroupDefined,
    GroupDeleted,
    Invalid,
    Member,
    MemberAdded,
    MemberRemoved,
    Resource,
    Revoked,
    TenantCreated,
    User,
)
from grantr.grants import Grants, InMemoryStorage
from tests.catalogs import ARTIFACTR, PORTALR, REFLEXR
from tests.grants.conftest import ALICE, ROOT

ACME = "acme"
WS = Resource(kind="workspace", workspace="w1")
BOB = User(id="bob")
CAROL = User(id="carol")
USERS = (ROOT, ALICE, BOB, CAROL)
"""ROOT is the deployment's operator, who may enter the tenant by granting themselves a role."""

TEAM = Group(id="team")
ROLES = (("owner", TENANT), ("admin", TENANT), ("admin", WS), ("editor", WS), ("viewer", WS))
CATALOG = Catalog.of(ARTIFACTR, REFLEXR, PORTALR)

type Refusal = type[Forbidden | Invalid] | None


def around(on: Resource) -> tuple[Resource, ...]:
    """The resources whose grants hold on a resource: itself, and the tenant it is in."""
    return (TENANT,) if on == TENANT else (TENANT, on)


def actions(grant: Grant) -> frozenset[str]:
    return CATALOG.role(grant.role, grant.on.kind, {}) or frozenset()


def granted(role: str, on: Resource, to: Grantee) -> Grant:
    return Grant(tenant=ACME, role=role, on=on, to=to)


def membership(member: Grantee) -> Grant:
    return granted("member", TENANT, member)


def refused(*reasons: tuple[bool, type[Forbidden | Invalid]]) -> Refusal:
    """The first refusal whose condition holds, in the order the command checks them."""
    return next((error for applies, error in reasons if applies), None)


@dataclass
class Access:
    """The model: a tenant's grants, and its groups' members."""

    grants: frozenset[Grant] = frozenset()
    groups: dict[str, frozenset[Member]] = field(default_factory=dict[str, frozenset[Member]])

    def members(self) -> list[User]:
        return [user for user in USERS if membership(user) in self.grants]

    def held(self, subject: User, on: Resource) -> frozenset[str]:
        """The actions a subject holds on a resource, by its grants and its groups'."""
        holders = [
            subject,
            *(Group(id=g) for g, members in self.groups.items() if subject in members),
        ]
        found = (actions(g) for g in self.grants if g.to in holders and g.on in around(on))
        return frozenset[str]().union(*found)

    def lacks(self, by: User, action: str, on: Resource) -> bool:
        return action not in self.held(by, on)

    def unbounded(self, by: User, grants: Iterable[Grant]) -> bool:
        """Whether a change to these grants gives or takes more than ``by`` holds."""
        return any(not actions(g) <= self.held(by, g.on) for g in grants)

    def owners(self) -> frozenset[Grantee]:
        """The members who hold ``owner`` on the tenant, by a grant of their own or a group's."""
        found: set[Grantee] = set()
        for g in self.grants:
            if (g.role, g.on) == ("owner", TENANT):
                own = frozenset((g.to,))
                found |= self.groups.get(g.to.id, frozenset()) if isinstance(g.to, Group) else own
        return frozenset(found)

    def leaves_no_owner(self, change: Callable[["Access"], None]) -> bool:
        """Whether a change leaves no member holding ``owner``, where one did (ADR-0014)."""
        after = replace(self, groups=dict(self.groups))
        change(after)
        return bool(self.owners()) and not after.owners()

    def to(self, grantee: Grantee) -> list[Grant]:
        return [g for g in self.grants if g.to == grantee]

    def give(self, *grants: Grant) -> None:
        self.grants |= frozenset(grants)

    def take(self, grants: Iterable[Grant]) -> None:
        self.grants -= frozenset(grants)

    def remove_member(self, member: Member) -> None:
        self.take(self.to(member))
        self.groups = {g: members - frozenset((member,)) for g, members in self.groups.items()}

    def regroup(self, group: str, members: frozenset[Member]) -> None:
        self.groups[group] = members

    def delete_group(self, group: str) -> None:
        self.groups.pop(group, None)
        self.take(self.to(Group(id=group)))

    @classmethod
    def replay(cls, entries: Iterable[AuditEntry]) -> "Access":
        """The access a tenant's audit log says it has."""
        access = cls()
        for entry in entries:
            match entry.event:
                case TenantCreated(owner=owner):
                    access.give(
                        membership(User(id=owner)), granted("owner", TENANT, User(id=owner))
                    )
                case MemberAdded(member=member):
                    access.give(membership(member))
                case MemberRemoved(member=member):
                    access.remove_member(member)
                case GroupDefined(group=group, members=members):
                    access.groups[group] = members
                case GroupDeleted(group=group):
                    access.delete_group(group)
                case Granted(grant=grant):
                    access.give(grant)
                case Revoked(grant=grant):
                    access.take([grant])
                case event:
                    pytest.fail(f"a change the machine never makes: {event}")
        return access


users = st.sampled_from(USERS)
grantees = st.sampled_from([*USERS, TEAM])
roles = st.sampled_from(ROLES)


class AccessMachine(RuleBasedStateMachine):
    """grantr over memory, with ROOT its operator, and acme owned by Alice.

    At the start Bob is an owner too, through the group, and Carol the tenant's admin, so that
    the walk soon meets a group that carries grants, and commands their makers hold too little
    for; ROOT enters only by granting themselves a role.
    """

    def __init__(self) -> None:
        super().__init__()
        self.storage = InMemoryStorage()
        self.grants = Grants(self.storage, catalogs=[ARTIFACTR, REFLEXR, PORTALR])
        self.model = Access(frozenset((membership(ALICE), granted("owner", TENANT, ALICE))))
        self.loop = asyncio.new_event_loop()
        try:
            self.run(self.open())
        except BaseException:
            self.loop.close()  # teardown runs only for a machine that started
            raise

    async def open(self) -> None:
        """Make the tenant and its members, group and grants, in grantr and in the model."""
        await self.grants.first_operator(ROOT.id)
        await self.grants.create_tenant(ACME, owner=ALICE.id, by=ROOT)
        for member in (BOB, CAROL):
            await self.grants.add_member(ACME, member, by=ALICE)
            self.model.give(membership(member))
        await self.grants.define_group(ACME, TEAM, frozenset((BOB,)), by=ALICE)
        self.model.groups[TEAM.id] = frozenset((BOB,))
        for role, to in (("owner", TEAM), ("admin", CAROL)):
            await self.grants.grant(ACME, role, on=TENANT, to=to, by=ALICE)
            self.model.give(granted(role, TENANT, to))

    def teardown(self) -> None:
        self.loop.close()

    def run[T](self, command: Coroutine[Any, Any, T]) -> T:
        return self.loop.run_until_complete(command)

    def step(self, refusal: Refusal, command: Coroutine[Any, Any, object]) -> bool:
        """Make a command, refused as the model says, and say whether it was carried out.

        The model is left as it was by a refusal, so the invariants hold that it changed nothing
        and recorded nothing.
        """
        if refusal is None:
            self.run(command)
            return True
        with pytest.raises(refusal):
            self.run(command)
        return False

    @rule(member=users, by=users)
    def add_member(self, member: User, by: User) -> None:
        refusal = refused(
            (self.model.lacks(by, "grantr:add_member", TENANT), Forbidden),
            (member in self.model.members(), Invalid),
        )
        if self.step(refusal, self.grants.add_member(ACME, member, by=by)):
            self.model.give(membership(member))

    @rule(member=users, by=users)
    def remove_member(self, member: User, by: User) -> None:
        own = self.model.to(member)
        refusal = refused(
            (self.model.lacks(by, "grantr:remove_member", TENANT), Forbidden),
            (member not in self.model.members(), Invalid),
            (self.model.unbounded(by, own), Forbidden),
            (self.model.leaves_no_owner(lambda after: after.remove_member(member)), Invalid),
        )
        if self.step(refusal, self.grants.remove_member(ACME, member, by=by)):
            self.model.remove_member(member)

    @rule(data=st.data(), by=users)
    def define_group(self, data: st.DataObject, by: User) -> None:
        """Define the group, as often with members as with anyone."""
        within = self.model.members()
        anyone = st.frozensets(users)
        members = data.draw(st.frozensets(st.sampled_from(within)) | anyone if within else anyone)
        carried = self.model.to(TEAM)
        refusal = refused(
            (self.model.lacks(by, "grantr:manage_groups", TENANT), Forbidden),
            (not set(members) <= set(self.model.members()), Invalid),
            (self.model.unbounded(by, carried), Forbidden),
            (self.model.leaves_no_owner(lambda after: after.regroup(TEAM.id, members)), Invalid),
        )
        if self.step(refusal, self.grants.define_group(ACME, TEAM, members, by=by)):
            self.model.regroup(TEAM.id, members)

    @rule(by=users)
    def delete_group(self, by: User) -> None:
        carried = self.model.to(TEAM)
        refusal = refused(
            (self.model.lacks(by, "grantr:manage_groups", TENANT), Forbidden),
            (TEAM.id not in self.model.groups, Invalid),
            (self.model.unbounded(by, carried), Forbidden),
            (self.model.leaves_no_owner(lambda after: after.delete_group(TEAM.id)), Invalid),
        )
        if self.step(refusal, self.grants.delete_group(ACME, TEAM, by=by)):
            self.model.delete_group(TEAM.id)

    @rule(role=roles, to=grantees, by=users)
    def grant(self, role: tuple[str, Resource], to: Grantee, by: User) -> None:
        grant = granted(*role, to)
        operator = by == to == ROOT
        refusal = refused(
            (not operator and self.model.lacks(by, "grantr:grant", grant.on), Forbidden),
            (to == TEAM and TEAM.id not in self.model.groups, Invalid),
            (to != TEAM and not operator and to not in self.model.members(), Invalid),
            (grant in self.model.grants, Invalid),
            (not operator and self.model.unbounded(by, [grant]), Forbidden),
        )
        if self.step(refusal, self.grants.grant(ACME, grant.role, on=grant.on, to=to, by=by)):
            self.model.give(grant, *([membership(ROOT)] if operator else []))

    @rule(data=st.data(), by=users)
    def revoke(self, data: st.DataObject, by: User) -> None:
        """Revoke a grant, as often one that is given as any other."""
        given = sorted((g for g in self.model.grants if g.role != "member"), key=str)
        anything = st.tuples(roles, grantees).map(lambda drawn: granted(*drawn[0], drawn[1]))
        grant = data.draw(st.sampled_from(given) | anything if given else anything)
        own = grant.to == by
        refusal = refused(
            (not own and self.model.lacks(by, "grantr:revoke", grant.on), Forbidden),
            (grant not in self.model.grants, Invalid),
            (not own and self.model.unbounded(by, [grant]), Forbidden),
            (self.model.leaves_no_owner(lambda after: after.take([grant])), Invalid),
        )
        command = self.grants.revoke(ACME, grant.role, on=grant.on, to=grant.to, by=by)
        if self.step(refusal, command):
            self.model.take([grant])

    @rule(
        subject=users,
        action=st.sampled_from(sorted(CATALOG.actions)),
        on=st.sampled_from([TENANT, WS]),
    )
    def check(self, subject: User, action: str, on: Resource) -> None:
        async def checked() -> tuple[bool, bool]:
            before = await self.storage.audit(ACME)
            allowed = await self.grants.check(ACME, subject, action, on)
            return allowed, await self.storage.audit(ACME) == before

        allowed, unchanged = self.run(checked())
        assert allowed == (action in self.model.held(subject, on))
        assert unchanged, "a check writes nothing"

    @invariant()
    def a_member_holds_owner(self) -> None:
        owners = self.model.owners()
        assert owners, "a member holds owner, through a group or not"
        assert set(owners) <= set(self.model.members())

    @invariant()
    def the_store_and_its_audit_log_hold_the_models_access(self) -> None:
        async def stored() -> tuple[Access, Access]:
            grants = frozenset(await self.storage.grants_in(ACME))
            held = Access(grants, await self.storage.groups(ACME))
            return held, Access.replay(await self.storage.audit(ACME))

        held, replayed = self.run(stored())
        assert held == self.model
        assert replayed == self.model, "the audit log replays to the same access"


AccessMachine.TestCase.settings = settings(max_examples=200, stateful_step_count=30, deadline=None)

TestAccessMachine = pytest.mark.timeout(300, method="thread")(AccessMachine.TestCase)
"""Its 200 examples take 4 s on a laptop's core, but on CI's four cores, against PostgreSQL and
beside three other workers, they ran past the suite's 60 s (run 39555510568, which ended its
worker): five minutes, five times what ended it; and the thread method, as Hypothesis replays a
failure once a signal's timer is spent (lattice ADR-0028)."""
