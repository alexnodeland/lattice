"""The layering in grantr's architecture, enforced.

The core has no I/O and imports only pydantic; grants imports the core, and lattice-core's
registry of integrations, its settings, and its approvals and capabilities, the contract the
store of approvals implements; sql imports lattice-core's approvals too, which it stores. grantr
imports neither artifactr nor reflexr, nor any sibling but lattice-core: the libraries' types
reach it structurally.
"""

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src" / "grantr"

OTEL_API = {"opentelemetry.metrics", "opentelemetry.trace"}
"""The OpenTelemetry API: the port grantr records through."""

LAYERS: dict[str, tuple[set[str], set[str]]] = {
    # layer: (grantr packages it may import, third-party modules it may import)
    # Settings are declared in lattice-core, which says how a layer narrows another: pure code.
    "core": ({"grantr.core"}, {"pydantic", "lattice_core.settings"}),
    "grants": (
        {"grantr.core", "grantr.grants", "grantr.telemetry"},
        {
            *OTEL_API,
            "lattice_core.integrations",
            "lattice_core.settings",
            "lattice_core.approvals",
            "lattice_core.capabilities",
        },
    ),
    "telemetry": ({"grantr.core", "grantr.telemetry"}, {"opentelemetry", *OTEL_API}),
    "testing": ({"grantr.core", "grantr.testing"}, set()),
    "fastapi": (
        {"grantr.core", "grantr.grants", "grantr.fastapi"},
        {"fastapi", "starlette", "pydantic"},
    ),
    "sql": (
        {"grantr.core", "grantr.sql"},
        {"pydantic", "sqlalchemy", "alembic", "lattice_core.sql", "lattice_core.approvals"},
    ),
}

IO = {"asyncio", "socket", "os", "pathlib", "subprocess", "io", "logging", "sqlite3"}
"""Standard modules the core may not import: it decides, and reads and writes nothing."""


def _imports(path: Path) -> set[str]:
    """Every module a file imports, with ``from m import n`` counted as ``m.n``."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _within(name: str, prefixes: set[str]) -> bool:
    return any(name == p or name.startswith(f"{p}.") for p in prefixes)


@pytest.mark.parametrize("layer", sorted(LAYERS))
def test_layer_imports_only_what_it_may(layer: str) -> None:
    own, third_party = LAYERS[layer]
    modules = sorted((SRC / layer).rglob("*.py"))
    assert modules, f"layer {layer} has no modules"
    for path in modules:
        for name in _imports(path):
            root = name.split(".")[0]
            where = f"{path.relative_to(SRC)} imports {name}"
            if root in sys.stdlib_module_names:
                assert layer != "core" or root not in IO, f"{where}: I/O in the core"
            elif root == "grantr":
                assert _within(name, own), f"{where}: above"
            else:
                assert _within(name, third_party), f"{where}: not a dependency of this layer"


def test_every_package_is_a_layer() -> None:
    packages = {path.name for path in SRC.iterdir() if (path / "__init__.py").exists()}
    assert packages == set(LAYERS)
