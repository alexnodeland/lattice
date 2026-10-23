"""lattice-core's settings: typed, declared once, each layer only narrowing the one above."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lattice_core.settings import (
    CONNECTED_TOOLS,
    KNOWN_SETTINGS,
    IntRange,
    Setting,
    SettingsDefaults,
    Subset,
    floor,
    operator_layer,
    registry,
)

LIMIT = KNOWN_SETTINGS["connect-per-hour:freecad"]
TOOLS = Setting(
    "connect-tools:fake",
    Subset(frozenset({"read", "edit", "run"})),
    default=("edit", "read", "run"),
    lowest="workspace",
    description="The fake's tools a workspace offers.",
)


def test_lattices_settings_are_each_apps_hourly_tries() -> None:
    assert list(KNOWN_SETTINGS) == [
        "connect-per-hour:freecad",
        "connect-per-hour:blender",
        "connect-tools:freecad",
        "connect-tools:blender",
    ]
    for app in ("freecad", "blender"):
        tools = KNOWN_SETTINGS[f"connect-tools:{app}"]
        assert tools.kind == Subset(CONNECTED_TOOLS[app])
        assert (tools.lowest, tools.default) == ("workspace", tuple(sorted(CONNECTED_TOOLS[app])))
    assert (LIMIT.kind, LIMIT.default, LIMIT.lowest) == (IntRange(0, 1000), 30, "workspace")


@pytest.mark.parametrize("given", [True, 1.5, "30", None, -1, 1001, [30], {"v": 1}])
def test_a_number_is_a_whole_one_within_its_bounds(given: object) -> None:
    with pytest.raises(ValueError, match=r"a whole number|from 0 to 1000"):
        LIMIT.value(given)


@pytest.mark.parametrize(
    "given", ["read", [1], ["read", "read"], ["read", "rm -rf /"], [None], {"read": 1}]
)
def test_a_subset_is_names_it_knows_each_once(given: object) -> None:
    with pytest.raises(ValueError, match=r"a list of names|names it knows"):
        TOOLS.value(given)


def test_a_subset_is_kept_sorted() -> None:
    assert TOOLS.value(["run", "read"]) == ("read", "run")


def test_a_setting_is_declared_well() -> None:
    with pytest.raises(ValueError, match="a name or family:name"):
        Setting("Two:colons:here", IntRange(0, 1), 0, "tenant", "x")
    with pytest.raises(ValueError, match="needs a description"):
        Setting("a", IntRange(0, 1), 0, "tenant", " ")
    with pytest.raises(ValueError, match="a's default isn't from 0 to 1"):
        Setting("a", IntRange(0, 1), 2, "tenant", "A.")
    with pytest.raises(ValueError, match="runs up"):
        IntRange(2, 1)
    with pytest.raises(ValueError, match="declared twice"):
        registry(LIMIT, LIMIT)


def test_who_may_set_a_setting() -> None:
    operator_only = Setting("a", IntRange(0, 9), 1, "operator", "A.")
    assert [operator_only.settable_by(t) for t in ("operator", "tenant", "workspace")] == [
        True,
        False,
        False,
    ]
    assert LIMIT.settable_by("workspace")


def test_the_operators_values_are_checked_as_the_deployment_starts() -> None:
    assert operator_layer(KNOWN_SETTINGS, {LIMIT.key: 60}) == {LIMIT.key: 60}
    with pytest.raises(ValueError, match="no registry declares: nope"):
        operator_layer(KNOWN_SETTINGS, {"nope": 1})
    with pytest.raises(ValueError, match="connect-per-hour:freecad is from 0 to 1000"):
        operator_layer(KNOWN_SETTINGS, {LIMIT.key: 5000})


async def test_without_a_store_the_operators_value_or_the_default() -> None:
    assert await SettingsDefaults().value("t", "w", LIMIT.key) == 30
    defaults = SettingsDefaults(operator={LIMIT.key: 60})
    assert await defaults.value("t", "w", LIMIT.key) == 60
    with pytest.raises(KeyError):
        await defaults.value("t", "w", "nope")


def test_the_floor_is_the_narrowest_value() -> None:
    assert (floor(LIMIT), floor(TOOLS)) == (0, ())


@given(
    st.integers(0, 1000),
    st.none() | st.integers(0, 1000),
    st.none() | st.integers(0, 1000),
)
def test_a_number_is_never_wider_than_a_layer_above(
    operator: int, tenant: int | None, workspace: int | None
) -> None:
    on_tenant = LIMIT.narrow(operator, tenant)
    effective = LIMIT.narrow(on_tenant, workspace)
    assert LIMIT.within(effective, on_tenant)
    assert LIMIT.within(on_tenant, operator)
    for layer in (tenant, workspace):
        if layer is not None:
            assert LIMIT.within(effective, layer)


NAMES = st.lists(st.sampled_from(["read", "edit", "run"]), unique=True).map(TOOLS.value)


@given(NAMES, st.none() | NAMES, st.none() | NAMES)
def test_a_subset_is_never_wider_than_a_layer_above(
    operator: tuple[str, ...], tenant: tuple[str, ...] | None, workspace: tuple[str, ...] | None
) -> None:
    effective = TOOLS.narrow(TOOLS.narrow(operator, tenant), workspace)
    assert TOOLS.within(effective, operator)
    for layer in (tenant, workspace):
        if layer is not None:
            assert TOOLS.within(effective, layer)


def test_a_value_of_the_wrong_kind_is_never_narrowed() -> None:
    with pytest.raises(TypeError, match="holds a number"):
        LIMIT.narrow(30, ("read",))
    with pytest.raises(TypeError, match="holds names"):
        TOOLS.within(3, ("read",))


@pytest.mark.parametrize(
    ("stored", "kept"),
    [(800, 800), (5000, 1000), (-3, 0), (True, 0), ("30", 0), (None, 0), ([30], 0)],
)
def test_a_stored_number_is_kept_within_todays_bounds(stored: object, kept: int) -> None:
    assert LIMIT.kept(stored) == kept


@pytest.mark.parametrize(
    ("stored", "kept"),
    [
        (["read", "run"], ("read", "run")),
        (["read", "gone"], ("read",)),
        (["gone"], ()),
        ([1], ()),
        ("read", ()),
        (None, ()),
    ],
)
def test_stored_names_are_kept_to_those_known_today(stored: object, kept: tuple[str, ...]) -> None:
    assert TOOLS.kept(stored) == kept


def test_a_stored_number_is_clamped_into_a_changed_range_both_ways() -> None:
    raised = Setting("a", IntRange(10, 500), 100, "workspace", "A.")
    assert raised.kept(5) == 10, "a registry that raises its lowest permits no less"
    assert raised.kept(800) == 500
