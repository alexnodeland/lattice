"""Integrations' settings as a state machine, and a store that can't be read.

Each step sets an integration on a tenant or in a workspace, on, off or unset, by a random
subject, in one of two tenants. The model predicts whether grantr refuses it, and records each
real change; a setting that is set already, or an unsetting of what isn't, changes nothing.
After every step each tenant's audit log holds one ``integration_set`` entry per real change in
it, in order, naming who and where; replaying them gives the store's settings; and
``is_enabled`` is wired to the stored levels (ADR-0034).
"""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, override

import pytest
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from grantr.core import (
    AuditEntry,
    AuditFilter,
    Forbidden,
    IntegrationSet,
    IntegrationSetting,
    Resource,
    User,
    WorkspaceId,
    effective,
)
from grantr.grants import Grants, InMemoryStorage
from lattice_core.integrations import KNOWN
from tests.catalogs import ARTIFACTR
from tests.grants.conftest import ALICE, ROOT

BOB = User(id="bob")
"""acme's w1's admin."""

CAROL = User(id="carol")
"""globex's owner."""

TENANTS = ("acme", "globex")
WORKSPACES: tuple[WorkspaceId | None, ...] = (None, "w1", "w2")
KEYS = ("excalidraw", "ui:mini-apps")
SET_ONLY = AuditFilter(types=frozenset({"integration_set"}))

type Level = tuple[str, WorkspaceId | None, str]
"""Where a setting is: its tenant, its workspace or None for the tenant's, and its key."""


def may(by: User, tenant: str, workspace: WorkspaceId | None) -> bool:
    """Whether a subject holds ``grantr:manage_integrations`` there."""
    owner = {"acme": ALICE, "globex": CAROL}[tenant]
    return by == owner or (tenant, workspace, by) == ("acme", "w1", BOB)


def replay(entries: list[AuditEntry]) -> dict[tuple[WorkspaceId | None, str], bool]:
    """The settings a tenant's ``integration_set`` entries leave."""
    settings: dict[tuple[WorkspaceId | None, str], bool] = {}
    for entry in entries:
        assert isinstance(entry.event, IntegrationSet)
        at = (entry.event.workspace, entry.event.key)
        if entry.event.on is None:
            settings.pop(at, None)
        else:
            settings[at] = entry.event.on
    return settings


class IntegrationsMachine(RuleBasedStateMachine):
    """grantr over memory: acme owned by Alice, with Bob w1's admin, and globex by Carol."""

    def __init__(self) -> None:
        super().__init__()
        self.storage = InMemoryStorage()
        self.grants = Grants(self.storage, catalogs=[ARTIFACTR])
        self.model: dict[Level, IntegrationSetting] = {}
        self.changes: dict[str, list[tuple[User, WorkspaceId | None, str, bool | None]]] = {
            tenant: [] for tenant in TENANTS
        }
        self.loop = asyncio.new_event_loop()
        try:
            self.run(self.open())
        except BaseException:
            self.loop.close()  # teardown runs only for a machine that started
            raise

    async def open(self) -> None:
        await self.grants.first_operator(ROOT.id)
        await self.grants.create_tenant("acme", owner=ALICE.id, by=ROOT)
        await self.grants.create_tenant("globex", owner=CAROL.id, by=ROOT)
        await self.grants.add_member("acme", BOB, by=ALICE)
        w1 = Resource(kind="workspace", workspace="w1")
        await self.grants.grant("acme", "admin", on=w1, to=BOB, by=ALICE)

    def teardown(self) -> None:
        self.loop.close()

    def run[T](self, command: Coroutine[Any, Any, T]) -> T:
        return self.loop.run_until_complete(command)

    @rule(
        tenant=st.sampled_from(TENANTS),
        workspace=st.sampled_from(WORKSPACES),
        key=st.sampled_from(KEYS),
        on=st.none() | st.booleans(),
        by=st.sampled_from((ALICE, BOB, CAROL)),
    )
    def set_integration(
        self, tenant: str, workspace: WorkspaceId | None, key: str, on: bool | None, by: User
    ) -> None:
        command = self.grants.set_integration(tenant, key, on, workspace=workspace, by=by)
        if not may(by, tenant, workspace):
            with pytest.raises(Forbidden):
                self.run(command)
            return
        state = self.run(command)
        level = state.tenant if workspace is None else state.workspace
        stored = self.model.get((tenant, workspace, key))
        if on == (None if stored is None else stored.on):
            assert level == stored, "a repeated setting keeps who set it, and when"
            return
        self.changes[tenant].append((by, workspace, key, on))
        if level is None:
            assert on is None
            del self.model[tenant, workspace, key]
        else:
            assert (level.on, level.by) == (on, by)
            self.model[tenant, workspace, key] = level

    @invariant()
    def each_real_change_is_one_entry_naming_who_and_where(self) -> None:
        for tenant in TENANTS:
            entries = self.run(self.storage.audit(tenant, keep=SET_ONLY))
            recorded = [
                (entry.by, entry.event.workspace, entry.event.key, entry.event.on)
                for entry in entries
                if isinstance(entry.event, IntegrationSet)
            ]
            assert recorded == self.changes[tenant], "in order, and none for the other tenant"

    @invariant()
    def the_log_replays_to_the_stored_settings(self) -> None:
        for tenant in TENANTS:
            stored = {
                (workspace, key): setting.on
                for workspace in WORKSPACES
                for key, setting in self.run(self.storage.integrations(tenant, workspace)).items()
            }
            assert replay(self.run(self.storage.audit(tenant, keep=SET_ONLY))) == stored
            assert stored == {
                (workspace, key): setting.on
                for (t, workspace, key), setting in self.model.items()
                if t == tenant
            }

    @invariant()
    def is_enabled_is_wired_to_the_stored_levels(self) -> None:
        for tenant, workspace, key in (
            (t, w, k) for t in TENANTS for w in ("w1", "w2") for k in KEYS
        ):
            tenants = self.model.get((tenant, None, key))
            own = self.model.get((tenant, workspace, key))
            expected = effective(
                installed=True,
                default=KNOWN[key].default,
                tenant=None if tenants is None else tenants.on,
                workspace=None if own is None else own.on,
            )
            assert self.run(self.grants.is_enabled(tenant, workspace, key)) == expected


IntegrationsMachine.TestCase.settings = settings(
    max_examples=100, stateful_step_count=30, deadline=None
)
TestIntegrationsMachine = IntegrationsMachine.TestCase


class Unreadable(InMemoryStorage):
    """A store whose integrations' settings can't be read."""

    @override
    async def integrations(
        self, tenant: str, workspace: WorkspaceId | None = None
    ) -> dict[str, IntegrationSetting]:
        raise ConnectionError


async def test_a_store_that_cant_be_read_turns_every_integration_off(
    caplog: pytest.LogCaptureFixture,
) -> None:
    grants = Grants(Unreadable())
    with caplog.at_level(logging.WARNING, logger="grantr.grants.grants"):
        assert not await grants.is_enabled("acme", "w1", "excalidraw")
    assert caplog.messages == ["excalidraw is off: the store can't be read"]
