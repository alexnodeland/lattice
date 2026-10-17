"""Check-out records, on memory, SQLite and PostgreSQL."""

from datetime import timedelta

from artifactr.core import AgentActor, UserActor
from artifactr.workspace import Scope
from artifactr_files.checkouts import Checkout
from tests.clock import START
from tests.conftest import Stores
from tests.files_of import digest

ACME = Scope("acme", "w1")
ALICE = UserActor(id="alice", name="Alice")


def checkout(**changes: object) -> Checkout:
    made = Checkout(
        id="co_1",
        artifact_id="a1",
        base_version=3,
        base_sha256=digest("v3"),
        actor=ALICE,
        expires_at=START + timedelta(hours=8),
    )
    return made.model_copy(update=changes)


async def test_a_checkout_is_kept_and_replaced_by_its_id(stores: Stores) -> None:
    assert await stores.checkouts.get(ACME, "co_1") is None
    await stores.checkouts.save(ACME, checkout())
    assert await stores.checkouts.get(ACME, "co_1") == checkout()
    extended = checkout(expires_at=START + timedelta(hours=9))
    await stores.checkouts.save(ACME, extended)
    assert await stores.checkouts.get(ACME, "co_1") == extended


async def test_a_checkout_is_its_tenants_workspaces(stores: Stores) -> None:
    await stores.checkouts.save(ACME, checkout())
    assert await stores.checkouts.get(Scope("globex", "w1"), "co_1") is None
    assert await stores.checkouts.get(Scope("acme", "w2"), "co_1") is None


async def test_any_actor_round_trips(stores: Stores) -> None:
    agent = AgentActor(thread_id="t1", run_id="r1", on_behalf_of=ALICE)
    await stores.checkouts.save(ACME, checkout(actor=agent))
    found = await stores.checkouts.get(ACME, "co_1")
    assert found is not None
    assert found.actor == agent


def test_its_holder_names_the_checkout_and_who_has_it() -> None:
    assert checkout().holder == "checkout:co_1:user:alice"
