"""Adapters: declared by the package that provides them, found through entry points, checked
against the port versions they implement, and adding integrations only while installed
(lattice RFC-0011)."""

import sys
import types
from collections.abc import Iterable
from importlib.metadata import EntryPoint
from typing import Any

import pytest

from lattice_core import adapters
from lattice_core.adapters import (
    ADAPTER_KINDS,
    CONTRACT,
    GROUP,
    AdapterManifest,
    AdapterSpec,
    IncompatibleAdapter,
    contract_schema,
    discover,
    integrations,
    require,
    satisfies,
)
from lattice_core.capabilities import JsonObject
from lattice_core.egress import Purpose
from lattice_core.integrations import KNOWN, Integration
from lattice_core.settings import IntRange, Setting

VAULT_KEY = Integration(key="secrets:vault", default=False, description="Keep secrets in Vault.")


def build(config: JsonObject) -> object:
    return ("built", config)


def spec(**changes: Any) -> AdapterSpec:
    fields: dict[str, Any] = {
        "kind": "secrets",
        "name": "supabase-vault",
        "version": "0.3.0",
        "implements": {"secrets": ">=1,<2"},
        "factory": build,
    }
    return AdapterSpec(**(fields | changes))


# ─── Versions ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("version", "specifier", "holds"),
    [
        ("1.0.0", ">=1,<2", True),
        ("1.9.3", ">=1,<2", True),
        ("2.0.0", ">=1,<2", False),
        ("0.9.0", ">=1,<2", False),
        ("1.2.0", "==1.2", True),
        ("1.2.1", "==1.2", False),
        ("1.2.1", "!=1.2.0", True),
        ("1.2.0", "> 1.1, <= 1.2", True),
        ("2.0.0-rc.1", ">=2", True),
    ],
)
def test_a_version_satisfies_every_clause_of_a_specifier(
    version: str, specifier: str, holds: bool
) -> None:
    assert satisfies(version, specifier) is holds


@pytest.mark.parametrize(("version", "specifier"), [("1", ">=1"), ("1.0.0", "~1"), ("1.0.0", "")])
def test_a_malformed_version_or_specifier_is_refused(version: str, specifier: str) -> None:
    with pytest.raises(ValueError, match="version"):
        satisfies(version, specifier)


# ─── The spec ─────────────────────────────────────────────────────────────────


def test_a_spec_supports_the_port_versions_it_implements() -> None:
    vault = spec()
    assert vault.supports("secrets", "1.0.0")
    assert not vault.supports("secrets", "2.0.0")
    assert not vault.supports("sandbox", "1.0.0")
    assert require(vault, "secrets", "1.4.0") is vault
    with pytest.raises(IncompatibleAdapter, match="implements >=1,<2") as refused:
        require(vault, "secrets", "2.0.0")
    assert (refused.value.spec, refused.value.port, refused.value.version) == (
        vault,
        "secrets",
        "2.0.0",
    )
    with pytest.raises(IncompatibleAdapter, match="implements none of it"):
        require(vault, "sandbox", "1.0.0")


@pytest.mark.parametrize(
    ("changes", "says"),
    [
        ({"kind": "database"}, "kind is one of"),
        ({"name": "Supabase Vault"}, "lowercase"),
        ({"version": "0.3"}, "MAJOR.MINOR.PATCH"),
        ({"implements": {}}, "implements no port"),
        ({"implements": {"secrets": "1.x"}}, "specifier"),
    ],
)
def test_a_malformed_spec_is_refused(changes: dict[str, Any], says: str) -> None:
    with pytest.raises(ValueError, match=says):
        spec(**changes)


def test_a_manifest_is_the_spec_without_its_factory() -> None:
    limit = Setting(
        key="secrets:reads-per-minute",
        kind=IntRange(1, 600),
        default=60,
        lowest="operator",
        description="How many reads a minute.",
    )
    vault = spec(
        integrations=(VAULT_KEY,),
        settings=(limit,),
        config_schema={"type": "object"},
        egress=(Purpose(key="secrets:vault"),),
    )
    assert vault.factory({"url": "x"}) == ("built", {"url": "x"})
    assert vault.manifest() == AdapterManifest(
        kind="secrets",
        name="supabase-vault",
        version="0.3.0",
        implements={"secrets": ">=1,<2"},
        integrations=("secrets:vault",),
        settings=("secrets:reads-per-minute",),
        config_schema={"type": "object"},
        egress=(Purpose(key="secrets:vault"),),
    )


def test_the_kinds_are_the_ports_an_adapter_answers() -> None:
    assert ADAPTER_KINDS == (
        "secrets",
        "sandbox",
        "forge",
        "coding_agent",
        "ide",
        "connector",
        "search",
        "mcp_server",
    )


# ─── Integrations ─────────────────────────────────────────────────────────────


def test_an_adapters_integrations_exist_beside_the_known_ones_while_installed() -> None:
    composed = integrations([spec(integrations=(VAULT_KEY,))])
    assert list(composed) == [*KNOWN, "secrets:vault"]
    assert dict(integrations([])) == dict(KNOWN)
    assert dict(integrations([spec(integrations=(VAULT_KEY,))], known={})) == {
        "secrets:vault": VAULT_KEY
    }


def test_an_adapter_declaring_a_known_integration_is_refused() -> None:
    with pytest.raises(ValueError, match="declared twice"):
        integrations(
            [spec(integrations=(VAULT_KEY,)), spec(name="other", integrations=(VAULT_KEY,))]
        )


# ─── Discovery ────────────────────────────────────────────────────────────────


def installed(monkeypatch: pytest.MonkeyPatch, points: dict[str, object]) -> Iterable[EntryPoint]:
    """Install a module of the objects given, and entry points naming each in GROUP."""
    module = types.ModuleType("fake_adapters")
    for name, value in points.items():
        setattr(module, name, value)
    monkeypatch.setitem(sys.modules, "fake_adapters", module)
    found = [EntryPoint(name=name, value=f"fake_adapters:{name}", group=GROUP) for name in points]

    def entry_points(*, group: str) -> list[EntryPoint]:
        return found if group == GROUP else []

    monkeypatch.setattr(adapters, "entry_points", entry_points)
    return found


def test_discovery_loads_every_installed_adapter_by_its_names_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault, aws = spec(), spec(name="aws-secrets-manager")
    installed(monkeypatch, {"vault": vault, "aws": aws})
    assert discover() == (aws, vault)
    assert discover("lattice.other") == ()


def test_discovery_refuses_what_isnt_a_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    installed(monkeypatch, {"vault": object()})
    with pytest.raises(TypeError, match="not an adapter's spec"):
        discover()


def test_discovery_refuses_two_adapters_of_one_kind_and_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed(monkeypatch, {"one": spec(), "two": spec(version="0.4.0")})
    with pytest.raises(ValueError, match="two secrets adapters are named supabase-vault"):
        discover()


def test_two_kinds_may_share_a_name(monkeypatch: pytest.MonkeyPatch) -> None:
    secrets, sandbox = spec(name="local"), spec(name="local", kind="sandbox")
    installed(monkeypatch, {"a": secrets, "b": sandbox})
    assert discover() == (secrets, sandbox)


# ─── The contract ─────────────────────────────────────────────────────────────


def test_the_contracts_schema_is_a_manifests() -> None:
    schema = contract_schema()
    assert schema["title"] == f"lattice.adapters {CONTRACT}"
    assert schema["required"] == list(AdapterManifest.model_fields)
