"""The layering in relayr's architecture, enforced.

The ledger knows neither library; the events and the followers use only what the libraries
export: every name relayr imports from artifactr or reflexr is in its module's `__all__`.
"""

import ast
import importlib
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src" / "relayr"

LIBRARIES = {"artifactr", "reflexr", "evalr"}

LAYERS: dict[str, tuple[set[str], set[str]]] = {
    # layer: (relayr packages it may import, third-party modules it may import)
    "events": ({"relayr.events"}, {*LIBRARIES, "pydantic"}),
    "ledger": ({"relayr.ledger"}, {"pydantic"}),
    "sql": ({"relayr.ledger", "relayr.sql"}, {"sqlalchemy", "alembic", "lattice_core.sql"}),
    "inbound": (
        {"relayr.events", "relayr.ledger", "relayr.outbound", "relayr.telemetry", "relayr.inbound"},
        {*LIBRARIES, "opentelemetry"},
    ),
    "telemetry": ({"relayr.telemetry"}, {"opentelemetry"}),
    # Its contribution, on lattice-core's contract (lattice ADR-0020).
    "otel": (
        {"relayr.telemetry", "relayr.otel"},
        {"opentelemetry", "lattice_core.otel.contribution"},
    ),
    "langfuse": (
        {"relayr.events", "relayr.ledger", "relayr.outbound", "relayr.langfuse"},
        {*LIBRARIES, "langfuse"},
    ),
    "outbound": (
        {"relayr.events", "relayr.ledger", "relayr.outbound"},
        {*LIBRARIES, "pydantic", "pydantic_ai"},
    ),
    "evals": (
        {"relayr.events", "relayr.ledger", "relayr.outbound", "relayr.rules", "relayr.evals"},
        LIBRARIES,
    ),
    # The forms extra's: only it imports artifactr.ui (ADR-0033).
    "ui": ({"relayr.events", "relayr.ui"}, {*LIBRARIES, "pydantic"}),
    "rules": (
        {"relayr.events", "relayr.outbound", "relayr.rules"},
        {*LIBRARIES, "pydantic", "pydantic_ai"},
    ),
}


def _imports(path: Path) -> set[tuple[str, str | None]]:
    """Every module a file imports, with the name it takes from it, if it takes one."""
    found: set[tuple[str, str | None]] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update((alias.name, None) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.update((node.module, alias.name) for alias in node.names)
    return found


def _within(name: str, prefixes: set[str]) -> bool:
    return any(name == p or name.startswith(f"{p}.") for p in prefixes)


@pytest.mark.parametrize("layer", sorted(LAYERS))
def test_layer_imports_only_what_it_may(layer: str) -> None:
    own, third_party = LAYERS[layer]
    modules = sorted((SRC / layer).rglob("*.py"))
    assert modules, f"layer {layer} has no modules"
    for path in modules:
        for module, name in _imports(path):
            root = module.split(".")[0]
            where = f"{path.relative_to(SRC)} imports {module}"
            if root in sys.stdlib_module_names:
                continue
            if root == "relayr":
                assert _within(module, own), f"{where}: above"
            else:
                assert _within(module, third_party), f"{where}: not a dependency of this layer"
            if root in LIBRARIES and name is not None:
                exported = importlib.import_module(module).__all__
                assert name in exported, f"{where}.{name}: not the library's public API"


def test_every_package_is_a_layer() -> None:
    packages = {path.name for path in SRC.iterdir() if (path / "__init__.py").exists()}
    assert packages == set(LAYERS)


def test_only_the_forms_extra_imports_artifactr_ui() -> None:
    importers = sorted(
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if not path.is_relative_to(SRC / "ui")
        and any(_within(module, {"artifactr.ui"}) for module, _ in _imports(path))
    )
    assert importers == []
