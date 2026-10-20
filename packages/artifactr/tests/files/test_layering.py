"""The layering within the native files' package, `artifactr.files`, enforced.

The package depends inward only: every name it imports from the rest of artifactr is in its
module's `__all__` (lattice RFC-0003), only the agent's tools import the agent's, and
`tests/test_layering.py` holds the rest of artifactr to importing nothing of it. Within it, the
manifest knows no other layer, and only the SQL layer knows SQL.
"""

import ast
import importlib
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parents[2] / "src" / "artifactr" / "files"

LIBRARY = {"artifactr.core", "artifactr.workspace"}
"""What it may import of the rest of artifactr: these, by their `__all__`."""

LAYERS: dict[str, tuple[set[str], set[str]]] = {
    # layer: (artifactr.files packages it may import, the others it may import)
    "manifest": ({"artifactr.files.manifest"}, {*LIBRARY, "pydantic"}),
    "blobs": ({"artifactr.files.manifest", "artifactr.files.blobs"}, LIBRARY),
    "checkouts": (
        {"artifactr.files.manifest", "artifactr.files.checkouts"},
        {*LIBRARY, "pydantic"},
    ),
    "app": ({"artifactr.files.manifest", "artifactr.files.app"}, {"pydantic"}),
    # The crafting apps, and their CLIs' MCP servers spawned on this machine.
    "craft": (
        {"artifactr.files.manifest", "artifactr.files.app", "artifactr.files.craft"},
        {"pydantic", "mcp", "anyio", "lattice_core.integrations"},
    ),
    # An app's adapter knows the port, the crafting apps, and how its own app reads a file.
    "wordcraft": (
        {
            "artifactr.files.manifest",
            "artifactr.files.app",
            "artifactr.files.craft",
            "artifactr.files.wordcraft",
        },
        {"pydantic"},
    ),
    "cadcraft": (
        {
            "artifactr.files.manifest",
            "artifactr.files.app",
            "artifactr.files.craft",
            "artifactr.files.cadcraft",
        },
        {"pydantic"},
    ),
    "photocraft": (
        {
            "artifactr.files.manifest",
            "artifactr.files.app",
            "artifactr.files.craft",
            "artifactr.files.photocraft",
        },
        {"pydantic"},
    ),
    "vectorcraft": (
        {
            "artifactr.files.manifest",
            "artifactr.files.app",
            "artifactr.files.craft",
            "artifactr.files.vectorcraft",
        },
        {"pydantic"},
    ),
    "designcraft": (
        {
            "artifactr.files.manifest",
            "artifactr.files.app",
            "artifactr.files.craft",
            "artifactr.files.designcraft",
        },
        {"pydantic"},
    ),
    "native": (
        {
            "artifactr.files.manifest",
            "artifactr.files.blobs",
            "artifactr.files.checkouts",
            "artifactr.files.app",
            "artifactr.files.native",
        },
        {*LIBRARY, "pydantic", "lattice_core.integrations"},
    ),
    # The agent's tools, on pydantic-ai and the agent's Session, the one layer that knows them.
    "tools": (
        {
            "artifactr.files.manifest",
            "artifactr.files.app",
            "artifactr.files.native",
            "artifactr.files.tools",
        },
        {*LIBRARY, "artifactr.agent", "pydantic", "pydantic_ai"},
    ),
    # People's check-out and check-in over HTTP, on artifactr's router's auth and statuses.
    "fastapi": (
        {
            "artifactr.files.manifest",
            "artifactr.files.blobs",
            "artifactr.files.checkouts",
            "artifactr.files.app",
            "artifactr.files.native",
            "artifactr.files.craft",
            "artifactr.files.fastapi",
        },
        {
            *LIBRARY,
            *("artifactr.fastapi", "artifactr.telemetry", "lattice_core.refusals"),
            *("fastapi", "starlette", "pydantic"),
        },
    ),
    "sql": (
        {
            "artifactr.files.manifest",
            "artifactr.files.blobs",
            "artifactr.files.checkouts",
            "artifactr.files.sql",
        },
        {*LIBRARY, "sqlalchemy", "alembic", "lattice_core.sql"},
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
            if _within(module, {"artifactr.files"}):
                assert _within(module, own), f"{where}: above"
                continue
            assert _within(module, third_party), f"{where}: not a dependency of this layer"
            if root == "artifactr":
                assert module in third_party, f"{where}: not a public module"
            if root == "artifactr" and name is not None:
                exported = importlib.import_module(module).__all__
                assert name in exported, f"{where}.{name}: not artifactr's public API"


def test_every_package_is_a_layer() -> None:
    packages = {path.name for path in SRC.iterdir() if (path / "__init__.py").exists()}
    assert packages == set(LAYERS)


def test_the_package_root_imports_only_its_layers() -> None:
    for module, _ in _imports(SRC / "__init__.py"):
        assert _within(module, {f"artifactr.files.{layer}" for layer in LAYERS}), module
