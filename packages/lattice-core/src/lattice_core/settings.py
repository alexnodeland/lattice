"""Settings: typed values a deployment, a tenant and a workspace each may only narrow.

A setting is named by a key of the integrations' form, such as ``connect-per-hour:freecad``, and
declared once, in a registry, with its kind (a whole number within bounds, or some of a set of
known names), its default, the lowest tier that may set it and a sentence that says what it is:
:data:`KNOWN_SETTINGS` is lattice's, and an application that adds its own passes
:func:`registry` one more :class:`Setting` (lattice ADR-0030).

A value is resolved through four layers: the registry's default, the operator's value in the
deployment's configuration, which replaces it, then the tenant's and the workspace's, each of
which may only narrow the one above it: a number may only be lowered, a subset only shrunk. A
:class:`Superset` is the one kind narrowed the other way: its names are what each layer asks for,
such as the tiers that need a person's approval, so a lower layer may only add to them, and the
layers resolve as their union (lattice ADR-0038). A value that would widen its layer is refused
where it is written, and clamped where it is read, so an operator who lowers a ceiling later wins
over every stored value at once.

Before a package acts on a setting, it asks a :class:`Settings`. grantr's adapter answers from
its store; without one, :class:`Defaults` answers the default, or the operator's value. A
setting is never a secret and never free text: no kind holds either.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal, Protocol, cast

from lattice_core.capabilities import TIERS as CAPABILITY_TIERS
from lattice_core.integrations import KEY

__all__ = [
    "APPROVE_TIERS",
    "CONNECTED_TOOLS",
    "CONNECTED_TOOL_RISKS",
    "KNOWN_SETTINGS",
    "RISKS",
    "TIERS",
    "IntRange",
    "Kind",
    "Setting",
    "Settings",
    "SettingsDefaults",
    "Subset",
    "Superset",
    "Tier",
    "Value",
    "floor",
    "operator_layer",
    "registry",
]

Tier = Literal["operator", "tenant", "workspace"]
"""Who sets a layer: the deployment's operator, in its configuration, or a tenant's or a
workspace's admins."""

TIERS: Final[tuple[Tier, ...]] = ("operator", "tenant", "workspace")
"""The tiers, from the one that may set the most to the one that may set the least."""

Value = int | tuple[str, ...]
"""A setting's value: a whole number, or a subset's names, sorted."""


@dataclass(frozen=True)
class IntRange:
    """A whole number from ``low`` to ``high``, both included, which a lower tier may only lower.

    Raises:
        ValueError: If ``low`` is above ``high``.
    """

    low: int
    high: int

    def __post_init__(self) -> None:
        if self.low > self.high:
            raise ValueError(f"a range runs up, not from {self.low} to {self.high}")

    def value(self, given: object) -> int:
        """The value given, if it is a whole number within the bounds.

        Raises:
            ValueError: Saying why it isn't.
        """
        if isinstance(given, bool) or not isinstance(given, int):
            raise ValueError("a whole number")
        if not self.low <= given <= self.high:
            raise ValueError(f"from {self.low} to {self.high}")
        return given

    def narrow(self, above: int, below: int) -> int:
        """The narrower of two values: the lower."""
        return min(above, below)

    def within(self, value: int, ceiling: int) -> bool:
        """Whether a value is no wider than its ceiling: no higher."""
        return value <= ceiling


@dataclass(frozen=True)
class Subset:
    """Some of a set of known names, which a lower tier may only shrink."""

    universe: frozenset[str]

    def value(self, given: object) -> tuple[str, ...]:
        """The names given, sorted, if each is known and none is given twice.

        Raises:
            ValueError: Saying why it isn't.
        """
        return _names_given(self.universe, given)

    def narrow(self, above: tuple[str, ...], below: tuple[str, ...]) -> tuple[str, ...]:
        """The narrower of two values: the names in both."""
        return tuple(sorted(set(above) & set(below)))

    def within(self, value: tuple[str, ...], ceiling: tuple[str, ...]) -> bool:
        """Whether a value is no wider than its ceiling: none of its names are outside it."""
        return set(value) <= set(ceiling)


@dataclass(frozen=True)
class Superset:
    """Some of a set of known names that each tier asks for, which a lower tier may only add to.

    Its names are requirements, such as the capability tiers that need a person's approval: a
    layer narrows what may happen by asking more, so the layers resolve as their union, and the
    layer above's value is the least a lower one may set (lattice ADR-0038).
    """

    universe: frozenset[str]

    def value(self, given: object) -> tuple[str, ...]:
        """The names given, sorted, if each is known and none is given twice.

        Raises:
            ValueError: Saying why it isn't.
        """
        return _names_given(self.universe, given)

    def narrow(self, above: tuple[str, ...], below: tuple[str, ...]) -> tuple[str, ...]:
        """The narrower of two values: the names in either, since each asks for more."""
        return tuple(sorted(set(above) | set(below)))

    def within(self, value: tuple[str, ...], ceiling: tuple[str, ...]) -> bool:
        """Whether a value is no wider than the layer above's: it keeps every name of it."""
        return set(value) >= set(ceiling)


def _names_given(universe: frozenset[str], given: object) -> tuple[str, ...]:
    """The names given, sorted, if each is in the universe and none is given twice.

    Raises:
        ValueError: Saying why they aren't.
    """
    if not isinstance(given, list | tuple):
        raise ValueError("a list of names")
    names: list[object] = list(cast("list[object] | tuple[object, ...]", given))
    if not all(isinstance(name, str) for name in names) or len(set(names)) != len(names):
        raise ValueError("a list of names, each once")
    if unknown := sorted(str(name) for name in names if name not in universe):
        raise ValueError(f"names it knows, not {', '.join(n[:64] for n in unknown[:5])}")
    return tuple(sorted(str(name) for name in names))


Kind = IntRange | Subset | Superset
"""What a setting's value is, and how a lower tier narrows it."""


@dataclass(frozen=True)
class Setting:
    """One setting: its key, its kind, its default, the lowest tier that sets it, and what it is.

    Raises:
        ValueError: If the key isn't of the integrations' form, the description is empty, or the
            default isn't of the kind.
    """

    key: str
    kind: Kind
    default: Value
    lowest: Tier
    """The lowest tier that may set it: ``"operator"`` for configuration alone."""

    description: str
    """One sentence, for the admin who sets it."""

    labels: Mapping[str, str] = field(default_factory=dict[str, str])
    """What each of a subset's or superset's names is, in words, for the admin who chooses them:
    such as a tool's risk. Each label names one of its universe's names."""

    def __post_init__(self) -> None:
        if not KEY.fullmatch(self.key):
            raise ValueError(f"a setting's key is a name or family:name, not {self.key!r}")
        if not self.description.strip():
            raise ValueError(f"{self.key} needs a description")
        if isinstance(self.kind, Subset | Superset) and (
            stray := sorted(set(self.labels) - self.kind.universe)
        ):
            raise ValueError(f"{self.key} labels names it doesn't have: {', '.join(stray)}")
        try:
            self.value(self.default)
        except ValueError as error:
            raise ValueError(f"{self.key}'s default isn't {error}") from None

    def value(self, given: object) -> Value:
        """The value given, canonical, if it is of the setting's kind.

        Raises:
            ValueError: Saying what a value of the kind is.
        """
        return self.kind.value(given)

    def narrow(self, above: Value, below: Value | None) -> Value:
        """A layer's value, narrowed by the one below it; unset below leaves it as it is.

        A number is the lower, a subset's names those in both, and a superset's those in either.
        """
        if below is None:
            return above
        if isinstance(self.kind, IntRange):
            return self.kind.narrow(_int(above), _int(below))
        return self.kind.narrow(_names(above), _names(below))

    def within(self, value: Value, ceiling: Value) -> bool:
        """Whether a value narrows the layer above's, or equals it: never wider.

        The layer above's value is a ceiling for a number and a subset, and the least a superset
        may hold.
        """
        if isinstance(self.kind, IntRange):
            return self.kind.within(_int(value), _int(ceiling))
        return self.kind.within(_names(value), _names(ceiling))

    def kept(self, stored: object) -> Value:
        """A value stored under an earlier registry, as this one keeps it: never wider.

        A number is clamped into today's bounds: above them it is lowered to the highest, and
        below them raised to the lowest, which is a registry's deliberate widening; names this
        registry doesn't know are dropped, from a superset too, since none can be asked for; a
        value of another type isn't read at all, and is the setting's floor. An admin's read
        flags each such value as clamped.
        """
        if isinstance(self.kind, IntRange):
            if isinstance(stored, bool) or not isinstance(stored, int):
                return floor(self)
            # Clamped into today's bounds. A registry that raises its lowest widens what it
            # permits on purpose: a value below it can't be honoured, and its lowest applies.
            return max(self.kind.low, min(self.kind.high, stored))
        if not isinstance(stored, list | tuple):
            return floor(self)
        names: list[object] = list(cast("list[object] | tuple[object, ...]", stored))
        if not all(isinstance(name, str) for name in names):
            return floor(self)
        return tuple(sorted({str(name) for name in names} & self.kind.universe))

    def settable_by(self, tier: Tier) -> bool:
        """Whether a tier may set it: it, or one above it, is the lowest that may."""
        return TIERS.index(tier) <= TIERS.index(self.lowest)


def _int(value: Value) -> int:
    if not isinstance(value, int):
        raise TypeError("a number's setting holds a number")
    return value


def _names(value: Value) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError("a setting of names holds names")
    return value


def registry(*settings: Setting) -> Mapping[str, Setting]:
    """Return the settings by key, in the order given, read-only.

    Raises:
        ValueError: If two declare one key.
    """
    known: dict[str, Setting] = {}
    for setting in settings:
        if setting.key in known:
            raise ValueError(f"{setting.key} is declared twice")
        known[setting.key] = setting
    return MappingProxyType(known)


def _per_hour(app: str, title: str) -> Setting:
    return Setting(
        f"connect-per-hour:{app}",
        IntRange(0, 1000),
        default=30,
        lowest="workspace",
        description=(
            f"How many tries at code and network calls to a connected {title} a workspace may"
            " make an hour."
        ),
    )


RISKS: Final = MappingProxyType(
    {
        "read": "reads",
        "edit": "edits",
        "code": "runs code",
        "network": "downloads",
    }
)
"""Each tool's risk, as a connected app's vetted entry names it, in the words admin shows."""

CONNECTED_TOOL_RISKS: Final = MappingProxyType(
    {
        "freecad": MappingProxyType(
            {
                "create_document": "edit",
                "create_object": "edit",
                "delete_object": "edit",
                "edit_object": "edit",
                "execute_code": "code",
                "execute_code_async": "code",
                "get_async_status": "read",
                "get_object": "read",
                "get_objects": "read",
                "get_parts_list": "read",
                "get_rpc_status": "read",
                "get_view": "read",
                "list_documents": "read",
            }
        ),
        "blender": MappingProxyType(
            {
                "execute_blender_code": "code",
                "generate_3d": "network",
                "get_addon_status": "read",
                "get_scene_info": "read",
                "import_asset": "network",
                "look": "read",
                "search_assets": "network",
            }
        ),
    }
)
"""Each connected app's tools' risks, as its vetted entry names them; an artifactr test holds
them equal."""

CONNECTED_TOOLS: Final = MappingProxyType(
    {app: frozenset(risks) for app, risks in CONNECTED_TOOL_RISKS.items()}
)
"""Each connected app's tools a workspace may offer, by app: every tool its vetted entry in
artifactr.connect names but those that act on the runner's host. An artifactr test holds the
two lists equal, so a tool vetted later is added here too."""


def _tools(app: str, title: str) -> Setting:
    universe = CONNECTED_TOOLS[app]
    return Setting(
        f"connect-tools:{app}",
        Subset(universe),
        default=tuple(sorted(universe)),
        lowest="workspace",
        description=(
            f"Which of a connected {title}'s tools a workspace offers, of those its operator"
            " offers."
        ),
        labels={name: RISKS[risk] for name, risk in CONNECTED_TOOL_RISKS[app].items()},
    )


APPROVE_TIERS: Final = "approve:tiers"
"""The setting that names the capability tiers whose calls need a person's approval (lattice
RFC-0011's O5, ADR-0038)."""

_APPROVE_TIERS = Setting(
    APPROVE_TIERS,
    Superset(frozenset(CAPABILITY_TIERS)),
    default=("outbound", "run_code"),
    lowest="workspace",
    description=(
        "Which tiers of capability need a person's approval before an agent's call goes ahead;"
        " a tenant or workspace may add tiers, never take one away."
    ),
    labels={
        "read": "reads",
        "write": "writes",
        "run_code": "runs code",
        "outbound": "reaches outside",
    },
)

KNOWN_SETTINGS: Final = registry(
    _per_hour("freecad", "FreeCAD"),
    _per_hour("blender", "Blender"),
    _tools("freecad", "FreeCAD"),
    _tools("blender", "Blender"),
    _APPROVE_TIERS,
)
"""lattice's settings. A connected app vetted later adds its own ``connect-per-hour:<app>`` and
``connect-tools:<app>``; an application with ``admin_high`` capabilities adds
:func:`lattice_core.approvals.admin_high_approvers`'s."""


def operator_layer(
    known: Mapping[str, Setting], given: Mapping[str, object]
) -> Mapping[str, Value]:
    """The operator's values, canonical, checked against the registry as the deployment starts.

    Raises:
        ValueError: If a key isn't declared, or a value isn't of its setting's kind.
    """
    layer: dict[str, Value] = {}
    for key, value in given.items():
        setting = known.get(key)
        if setting is None:
            raise ValueError(f"sets a setting no registry declares: {key}")
        try:
            layer[key] = setting.value(value)
        except ValueError as error:
            raise ValueError(f"{key} is {error}") from None
    return MappingProxyType(layer)


class Settings(Protocol):
    """A setting's value in a tenant's workspace: the port its package asks, each time it acts.

    An implementation that can't read its store answers the narrowest value a setting may have,
    :func:`floor`'s: its kind's lowest number, no names of a subset, or every name of a superset,
    so a failure never widens what a workspace may do. Its
    arguments are positional, so an implementation names them as it likes.

    Raises:
        KeyError: For a key no registry it knows declares.
    """

    async def value(self, tenant_id: str, workspace_id: str, key: str, /) -> Value:
        """Return the setting's value in the tenant's workspace."""
        ...


class SettingsDefaults:
    """Each setting's default, or the operator's value, everywhere: the answer without a store.

    Args:
        known: The settings it knows; :data:`KNOWN_SETTINGS` if omitted.
        operator: The operator's values, by key, which replace the defaults.

    Raises:
        ValueError: If the operator sets a key ``known`` doesn't declare, or a value of the
            wrong kind.
    """

    def __init__(
        self,
        known: Mapping[str, Setting] = KNOWN_SETTINGS,
        operator: Mapping[str, object] = MappingProxyType({}),
    ) -> None:
        self._known = known
        self._operator = operator_layer(known, operator)

    async def value(self, _tenant_id: str, _workspace_id: str, key: str, /) -> Value:
        """Return the operator's value, or the default."""
        return self._operator.get(key, self._known[key].default)


def floor(setting: Setting) -> Value:
    """The narrowest value a setting may have: what an unreadable store answers.

    A number's lowest, a subset's no names, and a superset's every name: an unreadable store
    asks for everything.
    """
    if isinstance(setting.kind, IntRange):
        return setting.kind.low
    return tuple(sorted(setting.kind.universe)) if isinstance(setting.kind, Superset) else ()
