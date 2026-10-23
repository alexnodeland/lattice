"""Settings over every storage: each layer only narrows, versioned, audited (lattice ADR-0030).

Each test that takes ``grants`` runs against memory, SQLite, and PostgreSQL as its owner and as a
role its row-level security holds.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, cast

import pytest

from grantr.core import (
    AuditFilter,
    Forbidden,
    Invalid,
    Resource,
    SettingSet,
    Stale,
    User,
)
from grantr.grants import Grants, InMemoryStorage, Storage
from lattice_core.settings import KNOWN_SETTINGS, IntRange, Setting, Subset, registry
from tests.catalogs import ARTIFACTR, PORTALR, REFLEXR
from tests.grants.conftest import ALICE, ROOT

KEY = "connect-per-hour:freecad"
BOB = User(id="bob")
"""acme's w1's admin."""

CAROL = User(id="carol")
"""acme's w1's editor."""

DAVE = User(id="dave")
"""globex's owner."""

W1 = Resource(kind="workspace", workspace="w1")
SET_ONLY = AuditFilter(types=frozenset({"setting_set"}))


async def _people(grants: Grants) -> None:
    for member in (BOB, CAROL):
        await grants.add_member("acme", member, by=ALICE)
    await grants.grant("acme", "admin", on=W1, to=BOB, by=ALICE)
    await grants.grant("acme", "editor", on=W1, to=CAROL, by=ALICE)
    await grants.create_tenant("globex", owner=DAVE.id, by=ROOT)


async def _grants(storage: Storage, **options: Any) -> Grants:
    grants = Grants(storage, catalogs=[ARTIFACTR, REFLEXR, PORTALR], **options)
    await grants.first_operator(ROOT.id)
    await grants.create_tenant("acme", owner=ALICE.id, by=ROOT)
    await _people(grants)
    return grants


async def test_a_setting_narrows_down_each_level(storage: Storage) -> None:
    grants = await _grants(storage, operator_settings={KEY: 60})
    assert await grants.value("acme", "w1", KEY) == 60, "the operator's replaces the default"
    await grants.set_setting("acme", KEY, 40, by=ALICE)
    state = await grants.set_setting("acme", KEY, 10, workspace="w1", by=BOB)
    assert (state.effective, state.ceiling, state.ceiling_set_by) == (10, 40, "tenant")
    assert await grants.value("acme", "w1", KEY) == 10
    assert await grants.value("acme", "w2", KEY) == 40, "the workspace's alone"
    assert await grants.value("globex", "w1", KEY) == 60, "the tenant's alone"
    unset = await grants.set_setting("acme", KEY, None, workspace="w1", by=BOB)
    assert unset.workspace is None
    assert await grants.value("acme", "w1", KEY) == 40


async def test_a_raise_is_refused_naming_its_ceiling_and_who_set_it(storage: Storage) -> None:
    grants = await _grants(storage, operator_settings={KEY: 60})
    with pytest.raises(Invalid, match="may be at most 60 here: the operator's value"):
        await grants.set_setting("acme", KEY, 61, by=ALICE)
    await grants.set_setting("acme", KEY, 20, by=ALICE)
    with pytest.raises(Invalid, match="may be at most 20 here: the tenant's value"):
        await grants.set_setting("acme", KEY, 21, workspace="w1", by=BOB)
    plain = await _grants(InMemoryStorage())  # the default's, with no operator value
    with pytest.raises(Invalid, match="may be at most 30 here: the default's value"):
        await plain.set_setting("acme", KEY, 31, by=ALICE)


async def test_a_lowered_ceiling_wins_over_what_is_stored(storage: Storage) -> None:
    grants = await _grants(storage, operator_settings={KEY: 60})
    await grants.set_setting("acme", KEY, 50, by=ALICE)
    await grants.set_setting("acme", KEY, 45, workspace="w1", by=BOB)
    # The operator lowers the ceiling: a deployment restarted with less.
    lower = Grants(storage, catalogs=[ARTIFACTR], operator_settings={KEY: 25})
    assert await lower.value("acme", "w1", KEY) == 25
    view = await lower.settings("acme", workspace="w1", by=ALICE)
    [state] = [s for s in view.settings if s.key == KEY]
    assert state.workspace is not None
    assert state.tenant is not None
    assert (state.tenant.value, state.tenant.clamped) == (50, True)
    assert (state.workspace.value, state.workspace.clamped) == (45, True)
    assert state.effective == 25


async def test_each_change_is_versioned_and_a_stale_one_refused(storage: Storage) -> None:
    grants = await _grants(storage)
    first = await grants.set_setting("acme", KEY, 20, version=0, by=ALICE)
    assert first.version == 1
    with pytest.raises(Stale, match="at version 1 here, not 0"):
        await grants.set_setting("acme", KEY, 10, version=0, by=ALICE)
    unset = await grants.set_setting("acme", KEY, None, version=1, by=ALICE)
    assert unset.version == 2, "unsetting counts, so an older read stays stale"
    with pytest.raises(Stale):
        await grants.set_setting("acme", KEY, 10, version=1, by=ALICE)
    same = await grants.set_setting("acme", KEY, None, by=ALICE)
    assert same.version == 2, "setting what is set records nothing"


async def test_each_change_is_audited_with_its_old_and_new_values(storage: Storage) -> None:
    grants = await _grants(storage)
    await grants.set_setting("acme", KEY, 20, by=ALICE)
    await grants.set_setting("acme", KEY, 10, by=ALICE)
    await grants.set_setting("acme", KEY, 5, workspace="w1", by=BOB)
    await grants.set_setting("acme", KEY, None, by=ALICE)
    entries = await grants.audit("acme", by=ALICE, keep=SET_ONLY)
    assert [(e.by, e.event) for e in entries] == [
        (ALICE, SettingSet(workspace=None, key=KEY, old=None, new=20, version=1)),
        (ALICE, SettingSet(workspace=None, key=KEY, old=20, new=10, version=2)),
        (BOB, SettingSet(workspace="w1", key=KEY, old=None, new=5, version=1)),
        (ALICE, SettingSet(workspace=None, key=KEY, old=10, new=None, version=3)),
    ]


async def test_who_may_narrow_a_setting(storage: Storage) -> None:
    grants = await _grants(storage)
    with pytest.raises(Forbidden):
        await grants.set_setting("acme", KEY, 1, workspace="w1", by=CAROL)
    with pytest.raises(Forbidden):  # a workspace's admin, not the tenant's
        await grants.set_setting("acme", KEY, 1, by=BOB)
    with pytest.raises(Forbidden):
        await grants.set_setting("acme", KEY, 1, workspace="w2", by=BOB)
    with pytest.raises(Forbidden):  # another tenant's owner
        await grants.set_setting("acme", KEY, 1, by=DAVE)
    with pytest.raises(Forbidden):
        await grants.settings("acme", by=DAVE)
    with pytest.raises(Forbidden):
        await grants.settings("acme", workspace="w1", by=CAROL)


async def test_an_operators_setting_is_set_by_no_tenant(storage: Storage) -> None:
    known = registry(
        *KNOWN_SETTINGS.values(),
        Setting("retention", IntRange(1, 400), 395, "operator", "Days kept."),
        Setting("tenant-only", IntRange(0, 5), 5, "tenant", "A tenant's."),
    )
    grants = await _grants(storage, settings=known)
    with pytest.raises(Forbidden, match="retention is set by the operator alone"):
        await grants.set_setting("acme", "retention", 30, by=ALICE)
    with pytest.raises(Forbidden, match="tenant-only is set by the tenant alone"):
        await grants.set_setting("acme", "tenant-only", 1, workspace="w1", by=ALICE)
    assert (await grants.set_setting("acme", "tenant-only", 1, by=ALICE)).effective == 1


@pytest.mark.parametrize(
    "value",
    [True, "10", 1.5, -1, 1001, 10**30, [10], {"v": 10}, ["a"], "'; DROP TABLE x; --"],
)
async def test_a_value_not_of_its_kind_is_refused(storage: Storage, value: object) -> None:
    grants = await _grants(storage)
    with pytest.raises(Invalid, match=f"{KEY} is (a whole number|from 0 to 1000)"):
        await grants.set_setting("acme", KEY, value, by=ALICE)
    assert await grants.audit("acme", by=ALICE, keep=SET_ONLY) == [], "nothing recorded"


async def test_an_unknown_key_is_refused_and_a_stored_one_never_applied(storage: Storage) -> None:
    grants = await _grants(storage)
    with pytest.raises(Invalid, match="there is no such setting"):
        await grants.set_setting("acme", "nope", 1, by=ALICE)
    with pytest.raises(KeyError):
        await grants.value("acme", "w1", "nope")
    # A setting the registry dropped: its row stays, listed, never applied.
    extra = Setting("gone", IntRange(0, 9), 9, "tenant", "Dropped later.")
    before = Grants(
        storage, catalogs=[ARTIFACTR], settings=registry(*KNOWN_SETTINGS.values(), extra)
    )
    await before.set_setting("acme", "gone", 1, by=ALICE)
    after = Grants(storage, catalogs=[ARTIFACTR])
    view = await after.settings("acme", by=ALICE)
    assert view.unknown == ["gone"]
    assert "gone" not in [s.key for s in view.settings]


async def test_a_store_that_cant_be_read_answers_the_floor() -> None:
    class Broken(InMemoryStorage):
        async def settings(self, tenant: str, workspace: str | None = None) -> Any:
            raise OSError("down")

    grants = Grants(Broken())
    assert await grants.value("acme", "w1", KEY) == 0
    assert await grants.value("", "w1", KEY) == 0, "no tenant: the floor"
    assert await grants.value("acme", "", KEY) == 0, "no workspace: the floor"


async def test_one_tenants_settings_are_its_own(storage: Storage) -> None:
    grants = await _grants(storage)
    await grants.set_setting("acme", KEY, 3, by=ALICE)
    await grants.set_setting("acme", KEY, 2, workspace="w1", by=BOB)
    assert await grants.value("globex", "w1", KEY) == 30
    view = await grants.settings("globex", workspace="w1", by=DAVE)
    [state] = [s for s in view.settings if s.key == KEY]
    assert (state.tenant, state.workspace, state.effective) == (None, None, 30)
    await grants.delete_tenant("acme", by=ALICE)
    await grants.create_tenant("acme", owner=ALICE.id, by=ROOT)
    assert await grants.value("acme", "w1", KEY) == 30, "a deleted tenant's settings go with it"


async def test_a_changed_registry_never_widens_a_stored_value(storage: Storage) -> None:
    tools = Setting(
        "connect-tools:fake",
        Subset(frozenset({"read", "edit", "run"})),
        default=("edit", "read", "run"),
        lowest="workspace",
        description="The fake's tools.",
    )
    limit = Setting("limit", IntRange(0, 1000), 900, "workspace", "A limit.")
    before = await _grants(storage, settings=registry(tools, limit))
    state = await before.set_setting("acme", tools.key, ["read", "run"], by=ALICE)
    assert (state.kind.type, state.kind.universe, state.effective) == (
        "subset",
        ["edit", "read", "run"],
        ["read", "run"],
    )
    await before.set_setting("acme", "limit", 800, by=ALICE)
    # The registry drops `run`, and tightens the limit's bounds below what is stored.
    fewer = Setting(
        tools.key, Subset(frozenset({"read", "edit"})), ("edit", "read"), "workspace", "Fewer."
    )
    tighter = Setting("limit", IntRange(0, 500), 500, "workspace", "Tighter.")
    after = Grants(storage, catalogs=[ARTIFACTR], settings=registry(fewer, tighter))
    assert await after.value("acme", "w1", tools.key) == ("read",), "not the whole default"
    assert await after.value("acme", "w1", "limit") == 500, "clamped, not risen"
    view = await after.settings("acme", by=ALICE)
    assert [(s.tenant.value, s.tenant.clamped) for s in view.settings if s.tenant] == [
        (["read", "run"], True),
        (800, True),
    ], "what was set, flagged: today's registry keeps it narrower"
    assert [s.effective for s in view.settings] == [["read"], 500]


async def test_a_registry_raising_its_lowest_raises_a_value_below_it(storage: Storage) -> None:
    low = Setting("limit", IntRange(0, 1000), 100, "workspace", "A limit.")
    before = await _grants(storage, settings=registry(low))
    await before.set_setting("acme", "limit", 5, by=ALICE)
    raised = Setting("limit", IntRange(10, 1000), 100, "workspace", "At least 10.")
    after = Grants(storage, catalogs=[ARTIFACTR], settings=registry(raised))
    assert await after.value("acme", "w1", "limit") == 10, "the registry permits no less"
    [state] = (await after.settings("acme", by=ALICE)).settings
    assert state.tenant is not None
    assert (state.tenant.value, state.tenant.clamped, state.effective) == (5, True, 10)


async def test_a_stored_value_of_another_type_is_the_floor(storage: Storage) -> None:
    grants = await _grants(storage)
    await grants.set_setting("acme", KEY, 20, by=ALICE)
    row = (await storage.settings("acme"))[KEY]
    async with storage.transaction("acme") as tx:
        await tx.set_setting("acme", None, KEY, row.model_copy(update={"value": ["x"]}))
    assert await grants.value("acme", "w1", KEY) == 0


async def test_who_may_comes_before_what_is_asked(storage: Storage) -> None:
    grants = await _grants(storage)
    for key, value in (("nope", 1), (KEY, "not a number"), (KEY, 5000)):
        with pytest.raises(Forbidden):
            await grants.set_setting("acme", key, value, workspace="w1", by=CAROL)


async def test_a_name_too_long_to_store_is_refused(storage: Storage) -> None:
    grants = await _grants(storage)
    with pytest.raises(Invalid, match="at most 256 long"):
        await grants.set_setting("acme", KEY, 1, workspace="w" * 257, by=ALICE)
    with pytest.raises(Invalid, match="at most 256 long"):
        await grants.set_setting("acme", "k" * 257, 1, by=ALICE)


async def test_a_tenant_no_one_made_has_the_operators_value(storage: Storage) -> None:
    grants = await _grants(storage, operator_settings={KEY: 40})
    assert await grants.value("nobody", "w1", KEY) == 40
    assert await grants.value("bad~id", "w1", KEY) == 0, "a malformed id: the floor"


async def test_a_change_that_cant_be_stored_records_nothing(storage: Storage) -> None:
    class RefusingTransaction:
        """A transaction that takes everything but a setting's row."""

        def __init__(self, transaction: Any) -> None:
            self._transaction = transaction

        def __getattr__(self, name: str) -> Any:
            return getattr(self._transaction, name)

        async def set_setting(self, *_: Any) -> None:
            raise OSError("the disk is full")

    class Refusing:
        """The storage, on every backend, whose transactions refuse a setting's row."""

        def __getattr__(self, name: str) -> Any:
            return getattr(storage, name)

        @asynccontextmanager
        async def transaction(self, tenant: Any) -> AsyncGenerator[Any]:
            async with storage.transaction(tenant) as transaction:
                yield RefusingTransaction(transaction)

    grants = await _grants(cast("Storage", Refusing()))
    with pytest.raises(OSError, match="the disk is full"):
        await grants.set_setting("acme", KEY, 5, by=ALICE)
    assert await grants.audit("acme", by=ALICE, keep=SET_ONLY) == [], "the entry went with it"
    assert await grants.value("acme", "w1", KEY) == 30


async def test_names_stored_in_another_order_are_not_clamped(storage: Storage) -> None:
    tools = Setting(
        "connect-tools:fake",
        Subset(frozenset({"read", "edit", "run"})),
        default=("edit", "read", "run"),
        lowest="workspace",
        description="The fake's tools.",
    )
    grants = await _grants(storage, settings=registry(tools))
    await grants.set_setting("acme", tools.key, ["run", "read"], by=ALICE)
    row = (await storage.settings("acme"))[tools.key]
    async with storage.transaction("acme") as tx:
        await tx.set_setting(
            "acme", None, tools.key, row.model_copy(update={"value": ["run", "read"]})
        )
    [state] = (await grants.settings("acme", by=ALICE)).settings
    assert state.tenant is not None
    assert state.tenant.clamped is False


async def test_a_workspace_offers_only_tools_the_tenant_keeps(storage: Storage) -> None:
    key = "connect-tools:freecad"
    grants = await _grants(
        storage, operator_settings={key: ["get_objects", "get_view", "create_object"]}
    )
    await grants.set_setting("acme", key, ["get_objects", "get_view"], by=ALICE)
    with pytest.raises(
        Invalid, match="may be at most get_objects, get_view here: the tenant's value"
    ):
        await grants.set_setting("acme", key, ["create_object"], workspace="w1", by=BOB)
    await grants.set_setting("acme", key, ["get_view"], workspace="w1", by=BOB)
    assert await grants.value("acme", "w1", key) == ("get_view",)
    assert await grants.value("acme", "w2", key) == ("get_objects", "get_view")
    with pytest.raises(Invalid, match="names it knows, not rm"):
        await grants.set_setting("acme", key, ["rm"], by=ALICE)
