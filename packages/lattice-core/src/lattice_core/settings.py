"""Settings: typed values a deployment, a tenant and a workspace each may only narrow.

A setting is named by a key of the integrations' form, such as ``connect-per-hour:freecad``, and
declared once, in a registry, with its kind (a whole number within bounds, or a subset of known
names), its default, the lowest tier that may set it and a sentence that says what it is:
:data:`KNOWN_SETTINGS` is lattice's, and an application that adds its own passes
:func:`registry` one more :class:`Setting` (lattice ADR-0030).

A value is resolved through four layers: the registry's default, the operator's value in the
deployment's configuration, which replaces it, then the tenant's and the workspace's, each of
which may only narrow the one above it: a number may only be lowered, a subset only shrunk. A
value that would widen its layer is refused where it is written, and clamped where it is read,
so an operator who lowers a ceiling later wins over every stored value at once.

Before a package acts on a setting, it asks a :class:`Settings`. grantr's adapter answers from
its store; without one, :class:`Defaults` answers the default, or the operator's value. A
setting is never a secret and never free text: no kind holds either.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, Protocol, cast

from lattice_core.integrations import KEY

__all__ = [
    "KNOWN_SETTINGS",
    "TIERS",
    "IntRange",
    "Kind",
    "Setting",
    "Settings",
    "SettingsDefaults",
    "Subset",
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
        if not isinstance(given, list | tuple):
            raise ValueError("a list of names")
        names: list[object] = list(cast("list[object] | tuple[object, ...]", given))
        if not all(isinstance(name, str) for name in names) or len(set(names)) != len(names):
            raise ValueError("a list of names, each once")
        if unknown := sorted(str(name) for name in names if name not in self.universe):
            raise ValueError(f"names it knows, not {', '.join(n[:64] for n in unknown[:5])}")
        return tuple(sorted(str(name) for name in names))

    def narrow(self, above: tuple[str, ...], below: tuple[str, ...]) -> tuple[str, ...]:
        """The narrower of two values: the names in both."""
        return tuple(sorted(set(above) & set(below)))

    def within(self, value: tuple[str, ...], ceiling: tuple[str, ...]) -> bool:
        """Whether a value is no wider than its ceiling: none of its names are outside it."""
        return set(value) <= set(ceiling)


Kind = IntRange | Subset
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

    def __post_init__(self) -> None:
        if not KEY.fullmatch(self.key):
            raise ValueError(f"a setting's key is a name or family:name, not {self.key!r}")
        if not self.description.strip():
            raise ValueError(f"{self.key} needs a description")
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
        """A layer's value, narrowed by the one below it; unset below leaves it as it is."""
        if below is None:
            return above
        if isinstance(self.kind, IntRange):
            return self.kind.narrow(_int(above), _int(below))
        return self.kind.narrow(_names(above), _names(below))

    def within(self, value: Value, ceiling: Value) -> bool:
        """Whether a value narrows its ceiling, or equals it: never wider."""
        if isinstance(self.kind, IntRange):
            return self.kind.within(_int(value), _int(ceiling))
        return self.kind.within(_names(value), _names(ceiling))

    def settable_by(self, tier: Tier) -> bool:
        """Whether a tier may set it: it, or one above it, is the lowest that may."""
        return TIERS.index(tier) <= TIERS.index(self.lowest)


def _int(value: Value) -> int:
    if not isinstance(value, int):
        raise TypeError("a number's setting holds a number")
    return value


def _names(value: Value) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError("a subset's setting holds names")
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


KNOWN_SETTINGS: Final = registry(_per_hour("freecad", "FreeCAD"), _per_hour("blender", "Blender"))
"""lattice's settings. A connected app vetted later adds its own ``connect-per-hour:<app>``."""


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
    its kind's lowest number or no names, so a failure never widens what a workspace may do. Its
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
    """The narrowest value a setting may have: what an unreadable store answers."""
    return setting.kind.low if isinstance(setting.kind, IntRange) else ()
