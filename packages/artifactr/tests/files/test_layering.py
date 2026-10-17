"""The layering in artifactr-files' architecture, enforced.

The package depends inward only: every name it imports from artifactr is in its module's
`__all__`, and artifactr imports nothing of it (lattice RFC-0003). Within it, the manifest knows
no other layer, and only the SQL layer knows SQL.
"""

import ast
import importlib
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src" / "artifactr_files"
ARTIFACTR = Path(importlib.import_module("artifactr").__file__ or "").parent

LIBRARY = {"artifactr.core", "artifactr.workspace"}
"""What it may import of artifactr: these, and `artifactr` itself, by their `__all__`."""

LAYERS: dict[str, tuple[set[str], set[str]]] = {
    # layer: (artifactr_files packages it may import, third-party modules it may import)
    "manifest": ({"artifactr_files.manifest"}, {*LIBRARY, "pydantic"}),
    "blobs": ({"artifactr_files.manifest", "artifactr_files.blobs"}, LIBRARY),
    "checkouts": (
        {"artifactr_files.manifest", "artifactr_files.checkouts"},
        {*LIBRARY, "pydantic"},
    ),
    "app": ({"artifactr_files.manifest", "artifactr_files.app"}, {"pydantic"}),
    "files": (
        {
            "artifactr_files.manifest",
            "artifactr_files.blobs",
            "artifactr_files.checkouts",
            "artifactr_files.app",
            "artifactr_files.files",
        },
        {*LIBRARY, "pydantic"},
    ),
    "sql": (
        {
            "artifactr_files.manifest",
            "artifactr_files.blobs",
            "artifactr_files.checkouts",
            "artifactr_files.sql",
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
            if root == "artifactr_files":
                assert _within(module, own), f"{where}: above"
            else:
                assert _within(module, third_party), f"{where}: not a dependency of this layer"
            if root == "artifactr" and name is not None:
                exported = importlib.import_module(module).__all__
                assert name in exported, f"{where}.{name}: not artifactr's public API"


def test_every_package_is_a_layer() -> None:
    packages = {path.name for path in SRC.iterdir() if (path / "__init__.py").exists()}
    assert packages == set(LAYERS)


def test_the_package_root_imports_only_its_layers() -> None:
    for module, _ in _imports(SRC / "__init__.py"):
        assert module == "importlib.metadata" or _within(
            module, {f"artifactr_files.{layer}" for layer in LAYERS}
        ), module


def test_artifactr_imports_nothing_of_it() -> None:
    for path in ARTIFACTR.rglob("*.py"):
        assert not any(m.startswith("artifactr_files") for m, _ in _imports(path)), path
