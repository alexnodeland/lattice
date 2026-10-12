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

LIBRARIES = {"artifactr", "reflexr"}

LAYERS: dict[str, tuple[set[str], set[str]]] = {
    # layer: (relayr packages it may import, third-party modules it may import)
    "events": ({"relayr.events"}, {*LIBRARIES, "pydantic"}),
    "ledger": ({"relayr.ledger"}, {"pydantic"}),
    "sql": ({"relayr.ledger", "relayr.sql"}, {"sqlalchemy", "alembic"}),
    "inbound": ({"relayr.events", "relayr.ledger", "relayr.inbound"}, LIBRARIES),
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
