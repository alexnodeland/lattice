"""The libraries' hooks, answered by grantr without importing either library.

The access and actor types here have the shapes lattice RFC-0001 gives artifactr's and
reflexr's; grantr reads them by their fields' names.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime

import pytest

from grantr.core import TENANT, Agent, Grant, Grantee, Resource, Subject, User
from grantr.grants import Grants, InMemoryStorage
from tests.catalogs import ARTIFACTR, REFLEXR
from tests.grants.conftest import ALICE, ROOT


@dataclass(frozen=True)
class ArtifactrAccess:
    action: str
    thread_id: str | None = None
    artifact_id: str | None = None


@dataclass(frozen=True)
class ReflexrAccess:
    action: str
    rule: str | None = None


@dataclass(frozen=True)
class UserActor:
    id: str


@dataclass(frozen=True)
class AgentActor:
    on_behalf_of: UserActor | None


def subject_of(tenant: str, workspace: str | None, actor: UserActor | AgentActor) -> Subject:
    match actor:
        case UserActor(id=user) | AgentActor(on_behalf_of=UserActor(id=user)):
            return User(id=user)
        case AgentActor():
            return Agent()


@pytest.fixture
async def grants() -> Grants:
    grants = Grants(InMemoryStorage(), catalogs=[ARTIFACTR, REFLEXR])
    await grants.first_operator(ROOT.id)
    await grants.create_tenant("acme", owner=ALICE.id, by=ROOT)
    await grants.add_member("acme", User(id="bob"), by=ALICE)
    await grants.grant(
        "acme", "viewer", on=Resource(kind="workspace", workspace="w1"), to=User(id="bob"), by=ALICE
    )
    await grants.grant(
        "acme",
        "editor",
        on=Resource(kind="thread", workspace="w1", id="t1"),
        to=User(id="bob"),
        by=ALICE,
    )
    return grants


async def test_an_access_is_about_the_rule_it_names(grants: Grants) -> None:
    authorize = grants.hooks(subject_of).authorize
    bob = UserActor("bob")
    assert await authorize("acme", "w1", bob, ReflexrAccess("reflexr:read_runs", rule="ops:x"))
    assert not await authorize("acme", "w2", bob, ReflexrAccess("reflexr:read_runs", rule="ops:x"))


async def test_a_tenant_wide_access_is_about_the_tenant(grants: Grants) -> None:
    authorize = grants.hooks(subject_of).authorize
    alice = UserActor("alice")
    assert await authorize("acme", None, alice, ReflexrAccess("reflexr:read_rules", rule="ops:x"))


async def test_authorize_checks_the_subject_the_actor_maps_to(grants: Grants) -> None:
    authorize = grants.hooks(subject_of).authorize
    bob = UserActor("bob")
    assert await authorize("acme", "w1", bob, ArtifactrAccess("artifactr:read_artifacts"))
    assert await authorize("acme", "w1", AgentActor(bob), ArtifactrAccess("artifactr:open"))
    assert not await authorize("acme", "w1", AgentActor(None), ArtifactrAccess("artifactr:open"))
    assert not await authorize("acme", None, bob, ReflexrAccess("reflexr:read_rules"))
    assert await authorize("acme", None, UserActor("alice"), ReflexrAccess("reflexr:read_rules"))


async def test_authorize_needs_every_item_an_access_names(grants: Grants) -> None:
    authorize = grants.hooks(subject_of).authorize
    bob = UserActor("bob")
    post = "artifactr:post_message"
    assert await authorize("acme", "w1", bob, ArtifactrAccess(post, thread_id="t1"))
    assert not await authorize("acme", "w1", bob, ArtifactrAccess(post, thread_id="t2"))
    assert not await authorize(
        "acme", "w1", bob, ArtifactrAccess(post, thread_id="t1", artifact_id="a1")
    )


async def test_hidden_hides_nothing_yet(grants: Grants) -> None:
    hidden = await grants.hooks(subject_of).hidden("acme", "w1", UserActor("bob"))
    assert (hidden.threads, hidden.artifacts) == (frozenset(), frozenset())


class Unreadable(InMemoryStorage):
    """A store that can't be read."""

    async def grants(
        self, tenant: str | None, to: Grantee, *, on: Collection[Resource] | None = None
    ) -> list[Grant]:
        raise ConnectionError


async def test_a_store_that_cant_be_read_refuses() -> None:
    grants = Grants(Unreadable(), catalogs=[ARTIFACTR])
    assert not await grants.check("acme", ALICE, "artifactr:open", TENANT)


async def test_the_storage_stamps_entries_with_the_time() -> None:
    grants = Grants(InMemoryStorage())
    entry = await grants.first_operator(ROOT.id)
    assert entry.at.tzinfo is not None
    assert entry.at <= datetime.now(entry.at.tzinfo)
