"""Adapters: what answers a port in a deployment, how it is found, and which versions it takes.

An :class:`AdapterSpec` is an installed adapter, declared by the package that provides it: its
kind (the port it answers, such as ``secrets`` or ``forge``), its name, its distribution's
version, the port versions it implements, the integrations and settings it adds, the JSON
Schema of its configuration, the egress purposes it needs, and the factory that builds it from
that configuration. A package names its spec in its ``pyproject.toml``, in the entry-point
group :data:`GROUP`, so installing an extra registers its adapter, and :func:`discover` loads
every one installed (lattice RFC-0011).

The operator chooses which installed adapter answers each port; the application composes the
integrations an adapter adds with :data:`~lattice_core.integrations.KNOWN` through
:func:`integrations`, so they exist only while it is installed, and refuses at startup an
adapter whose ``implements`` doesn't cover the port's version (:func:`require`). The
conformance harness that checks an adapter against its port is not declared here yet.

The contract's version is :data:`CONTRACT`. Its JSON Schema is an :class:`AdapterManifest`'s,
the declarative part of a spec that portalr's admin shows, which :func:`contract_schema`
returns, checked in at ``schemas/adapters.v1.json``: regenerate it with ``moon run
lattice-core:schema`` (:mod:`lattice_core.contracts`).
"""

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from types import MappingProxyType
from typing import Final, Literal, get_args

from pydantic import BaseModel, ConfigDict, JsonValue

from lattice_core import integrations as known_integrations
from lattice_core.capabilities import VERSION, JsonObject
from lattice_core.egress import Purpose
from lattice_core.integrations import Integration
from lattice_core.settings import Setting

__all__ = [
    "ADAPTER_KINDS",
    "CONTRACT",
    "GROUP",
    "NAME",
    "SPECIFIER",
    "AdapterKind",
    "AdapterManifest",
    "AdapterSpec",
    "IncompatibleAdapter",
    "contract_schema",
    "discover",
    "integrations",
    "require",
    "satisfies",
]

CONTRACT: Final = "1.0.0"
"""The contract's version. A removed field or a changed meaning is a major version; an optional
field or a new :data:`AdapterKind` is a minor one."""

GROUP: Final = "lattice.adapters"
"""The entry-point group a package names its adapter's spec in, for :func:`discover`."""

AdapterKind = Literal[
    "secrets", "sandbox", "forge", "coding_agent", "ide", "connector", "search", "mcp_server"
]
"""The kind of port an adapter answers."""

ADAPTER_KINDS: Final[tuple[AdapterKind, ...]] = get_args(AdapterKind)
"""The kinds of port an adapter may answer."""

NAME: Final = re.compile(r"[a-z][a-z0-9-]*")
"""An adapter's name: lowercase letters, digits and hyphens, such as ``supabase-vault``."""

SPECIFIER: Final = re.compile(r"(>=|<=|==|!=|>|<)\s*([0-9]+(?:\.[0-9]+){0,2})")
"""One clause of a version specifier: an operator and a version of one to three numbers. A
specifier is clauses joined by commas, all of which must hold: ``>=1,<2``."""


def _numbers(version: str) -> tuple[int, int, int]:
    """Return a version's major, minor and patch, missing ones 0, without pre-release or build."""
    parts = re.split(r"[-+]", version, maxsplit=1)[0].split(".")
    major, minor, patch = (*(int(part) for part in parts), 0, 0)[:3]
    return major, minor, patch


def _clauses(specifier: str) -> list[tuple[str, tuple[int, int, int]]]:
    clauses: list[tuple[str, tuple[int, int, int]]] = []
    for clause in specifier.split(","):
        matched = SPECIFIER.fullmatch(clause.strip())
        if matched is None:
            raise ValueError(f"a version specifier is clauses such as >=1,<2, not {specifier!r}")
        clauses.append((matched[1], _numbers(matched[2])))
    return clauses


_COMPARE: Final[Mapping[str, Callable[[tuple[int, ...], tuple[int, ...]], bool]]] = (
    MappingProxyType(
        {
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
        }
    )
)


def satisfies(version: str, specifier: str) -> bool:
    """Whether a version meets every clause of a specifier, such as ``1.2.0`` and ``>=1,<2``.

    Raises:
        ValueError: If the version isn't a semantic version or the specifier isn't one.
    """
    if not VERSION.fullmatch(version):
        raise ValueError(f"a version is MAJOR.MINOR.PATCH, not {version!r}")
    numbers = _numbers(version)
    return all(_COMPARE[operator](numbers, bound) for operator, bound in _clauses(specifier))


class AdapterManifest(BaseModel):
    """What an adapter declares, as portalr's admin shows it: everything but its factory."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    kind: AdapterKind
    """The kind of port it answers."""
    name: str
    """Its name, such as ``supabase-vault``."""
    version: str
    """Its distribution's version."""
    implements: dict[str, str]
    """Each port it implements, by name, and the port versions it supports: ``>=1,<2``."""
    integrations: tuple[str, ...]
    """The keys of the integrations it adds (lattice ADR-0027)."""
    settings: tuple[str, ...]
    """The keys of the settings it adds (lattice ADR-0030)."""
    config_schema: JsonObject
    """The JSON Schema of its configuration, which startup validates."""
    egress: tuple[Purpose, ...]
    """The egress purposes it needs."""


@dataclass(frozen=True)
class AdapterSpec:
    """An adapter, as the package that provides it declares it.

    Raises:
        ValueError: If the kind isn't an :data:`AdapterKind`, the name isn't of :data:`NAME`'s
            form, the version isn't a semantic version, it implements no port, or a specifier
            is malformed.
    """

    kind: AdapterKind
    """The kind of port it answers."""
    name: str
    """Its name, such as ``supabase-vault``, ``opensandbox`` or ``forgejo``."""
    version: str
    """Its distribution's version."""
    implements: Mapping[str, str]
    """Each port it implements, by name, and the port versions it supports:
    ``{"secrets": ">=1,<2"}``."""
    factory: Callable[[JsonObject], object]
    """Builds it from its configuration, once validated against ``config_schema``."""
    integrations: tuple[Integration, ...] = ()
    """The integrations it adds, which exist only while it is installed."""
    settings: tuple[Setting, ...] = ()
    """The settings it adds."""
    config_schema: JsonObject = field(default_factory=dict[str, JsonValue])
    """The JSON Schema of its configuration."""
    egress: tuple[Purpose, ...] = ()
    """The egress purposes it needs to reach."""

    def __post_init__(self) -> None:
        if self.kind not in ADAPTER_KINDS:
            raise ValueError(f"an adapter's kind is one of {', '.join(ADAPTER_KINDS)}")
        if not NAME.fullmatch(self.name):
            raise ValueError(f"an adapter's name is lowercase and hyphens, not {self.name!r}")
        if not VERSION.fullmatch(self.version):
            raise ValueError(f"{self.name}'s version is MAJOR.MINOR.PATCH, not {self.version!r}")
        if not self.implements:
            raise ValueError(f"{self.name} implements no port")
        for specifier in self.implements.values():
            _clauses(specifier)

    def supports(self, port: str, version: str) -> bool:
        """Whether it implements the port at the version, such as ``secrets`` at ``1.0.0``."""
        specifier = self.implements.get(port)
        return specifier is not None and satisfies(version, specifier)

    def manifest(self) -> AdapterManifest:
        """Return what it declares, without its factory."""
        return AdapterManifest(
            kind=self.kind,
            name=self.name,
            version=self.version,
            implements=dict(self.implements),
            integrations=tuple(integration.key for integration in self.integrations),
            settings=tuple(setting.key for setting in self.settings),
            config_schema=self.config_schema,
            egress=self.egress,
        )


class IncompatibleAdapter(ValueError):
    """An adapter that doesn't implement the port's version, which startup refuses to enable.

    Args:
        spec: The adapter.
        port: The port's name.
        version: The port's version.
    """

    def __init__(self, spec: AdapterSpec, port: str, version: str) -> None:
        super().__init__(
            f"{spec.name} {spec.version} doesn't implement {port} {version}: it implements "
            f"{spec.implements.get(port, 'none of it')}"
        )
        self.spec = spec
        self.port = port
        self.version = version


def require(spec: AdapterSpec, port: str, version: str) -> AdapterSpec:
    """Return the adapter if it implements the port at the version.

    Raises:
        IncompatibleAdapter: If it doesn't.
    """
    if not spec.supports(port, version):
        raise IncompatibleAdapter(spec, port, version)
    return spec


def discover(group: str = GROUP) -> tuple[AdapterSpec, ...]:
    """Return the adapters installed packages name in the entry-point group, by their names.

    Args:
        group: The entry-point group; :data:`GROUP` if omitted.

    Raises:
        TypeError: If an entry point names something that isn't an :class:`AdapterSpec`.
        ValueError: If two adapters of one kind share a name.
    """
    found: dict[tuple[str, str], AdapterSpec] = {}
    for entry_point in sorted(entry_points(group=group), key=lambda point: point.name):
        loaded: object = entry_point.load()
        if not isinstance(loaded, AdapterSpec):
            raise TypeError(f"{entry_point.name} = {entry_point.value!r} is not an adapter's spec")
        if (loaded.kind, loaded.name) in found:
            raise ValueError(f"two {loaded.kind} adapters are named {loaded.name}")
        found[loaded.kind, loaded.name] = loaded
    return tuple(found.values())


def integrations(
    specs: Iterable[AdapterSpec],
    known: Mapping[str, Integration] = known_integrations.KNOWN,
) -> Mapping[str, Integration]:
    """Return the integrations a deployment has: the known ones, then each adapter's.

    Args:
        specs: The installed adapters.
        known: The integrations lattice declares; :data:`~lattice_core.integrations.KNOWN` if
            omitted.

    Raises:
        ValueError: If an adapter declares an integration already declared.
    """
    added = [integration for spec in specs for integration in spec.integrations]
    return known_integrations.registry(*known.values(), *added)


def contract_schema() -> dict[str, JsonValue]:
    """Return the contract's JSON Schema: an adapter's manifest."""
    schema = AdapterManifest.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"lattice.adapters {CONTRACT}",
        "description": (
            "lattice's adapter contract: what an installed adapter declares, as an operator "
            "sees it, without the factory that builds it."
        ),
        "type": "object",
        "properties": schema["properties"],
        "required": schema["required"],
        "$defs": schema["$defs"],
    }
