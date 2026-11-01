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
    "sql": (
        {"relayr.ledger", "relayr.sql"},
        {"pydantic", "sqlalchemy", "alembic", "lattice_core.sql"},
    ),
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
    # Whether an integration runs in a workspace without a store: lattice-core's port, answered.
    "integrations": ({"relayr.integrations"}, {"lattice_core.integrations"}),
    # The tracker connector (lattice RFC-0004): the port, the core, the followers and the fake;
    # and `http`, which only the adapters import, on httpx.
    "trackers": (
        {
            "relayr.integrations",
            "relayr.ledger",
            "relayr.outbound",
            "relayr.telemetry",
            "relayr.trackers",
        },
        {
            *LIBRARIES,
            "pydantic",
            "pydantic_ai",
            "httpx",
            "opentelemetry",
            "lattice_core.integrations",
        },
    ),
    # The trackers' webhooks' route and the connector's reads, on FastAPI and lattice-core's
    # refusals; the reads ask reflexr's `authorize`, as reflexr's routes do, and say whose
    # workspace each span read.
    "fastapi": (
        {"relayr.ledger", "relayr.telemetry", "relayr.trackers", "relayr.fastapi"},
        {
            "fastapi",
            "lattice_core.commands",
            "lattice_core.refusals",
            "opentelemetry",
            "pydantic",
            "reflexr",
        },
    ),
    "plane": ({"relayr.trackers", "relayr.plane"}, {"httpx", "pydantic"}),
    "vikunja": ({"relayr.trackers", "relayr.vikunja"}, {"httpx", "pydantic"}),
    # The forms extra's: only it imports artifactr.ui (ADR-0038).
    "ui": ({"relayr.events", "relayr.ui"}, {*LIBRARIES, "pydantic"}),
    # The excalidraw extra's: only it imports artifactr.excalidraw.
    "excalidraw": ({"relayr.events", "relayr.excalidraw"}, {*LIBRARIES, "pydantic"}),
    "rules": (
        {"relayr.events", "relayr.outbound", "relayr.rules"},
        {*LIBRARIES, "pydantic", "pydantic_ai"},
    ),
    # relayr's static catalog (lattice RFC-0014): commands declared on lattice-core's types,
    # reading nothing, so the parity test and the schema read it without a workspace.
    "commands": (
        {"relayr.commands"},
        {"pydantic", "lattice_core.capabilities", "lattice_core.commands"},
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


def test_only_the_excalidraw_extra_imports_artifactr_excalidraw() -> None:
    importing = [
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if not path.is_relative_to(SRC / "excalidraw")
        and any(_within(module, {"artifactr.excalidraw"}) for module, _ in _imports(path))
    ]
    assert importing == []
