"""grantr's ``Grants`` is lattice-core's ``Integrations``, the port relayr's trackers take.

grantr names no port, and imports no relayr: it meets the port by its shape. pyright checks the
assignment here, and the test the answers it gives, beside relayr's answer without a store.
"""

import asyncio

from grantr import Grants, InMemoryStorage, User
from lattice_core.integrations import Integrations
from relayr.integrations import ALWAYS

ROOT = User(id="root")
ALICE = User(id="alice")


async def _answers() -> tuple[bool, bool, bool, bool]:
    grants = Grants(InMemoryStorage())
    await grants.first_operator(ROOT.id)
    await grants.create_tenant("acme", owner=ALICE.id, by=ROOT)
    await grants.set_integration("acme", "tracker:plane", False, workspace="w1", by=ALICE)
    integrations: Integrations = grants
    return (
        await integrations.is_enabled("acme", "w1", "tracker:plane"),
        await integrations.is_enabled("acme", "w2", "tracker:plane"),
        await integrations.is_enabled("acme", "w1", "ui:mini-apps"),
        await ALWAYS.is_enabled("acme", "w1", "tracker:plane"),
    )


def test_grants_is_the_port_relayrs_trackers_take() -> None:
    assert asyncio.run(_answers()) == (False, True, False, True)
