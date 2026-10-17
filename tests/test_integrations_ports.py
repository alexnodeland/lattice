"""grantr's ``Grants`` is lattice-core's ``Integrations``, and ``is_enabled`` relayr's ``Enabled``.

grantr names neither port, and imports no relayr: it meets both by its shape. pyright checks the
assignments here, and the test the answers they give.
"""

import asyncio

from grantr import Grants, InMemoryStorage, User
from lattice_core.integrations import Integrations
from relayr.integrations import Enabled

ROOT = User(id="root")
ALICE = User(id="alice")


async def _answers() -> tuple[bool, bool, bool, bool]:
    grants = Grants(InMemoryStorage())
    await grants.first_operator(ROOT.id)
    await grants.create_tenant("acme", owner=ALICE.id, by=ROOT)
    await grants.set_integration("acme", "tracker:plane", False, workspace="w1", by=ALICE)
    integrations: Integrations = grants
    enabled: Enabled = grants.is_enabled
    return (
        await integrations.is_enabled("acme", "w1", "tracker:plane"),
        await enabled("acme", "w1", "tracker:plane"),
        await enabled("acme", "w2", "tracker:plane"),
        await integrations.is_enabled("acme", "w1", "ui:mini-apps"),
    )


def test_grants_is_lattice_cores_integrations_and_relayrs_enabled() -> None:
    assert asyncio.run(_answers()) == (False, False, True, False)
