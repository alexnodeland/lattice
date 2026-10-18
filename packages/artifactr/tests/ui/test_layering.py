"""artifactr.ui's layering, enforced (ADR-0074).

It is a plugin: nothing else in artifactr imports it, so an application that doesn't import it
registers none of its types. It depends inward only, on names in ``__all__`` of
``artifactr.core``, ``artifactr.agent`` and ``artifactr.workspace``; within it, the schema knows
no artifact type, and the types no agent. relayr bridges it, in ``relayr.ui``.
"""

import ast
import importlib
from pathlib import Path

import pytest

SRC = Path(__file__).parents[2] / "src" / "artifactr"
UI = SRC / "ui"

PUBLIC = {"artifactr.core", "artifactr.agent", "artifactr.workspace"}
"""The artifactr modules whose ``__all__`` artifactr.ui may import from."""

MODULES: dict[str, set[str]] = {
    # module: the artifactr.ui modules it may import
    "__init__": {"artifactr.ui"},
    "_common": set(),
    "_html": set(),
    "schema": {"artifactr.ui._common"},
    "ids": set(),
    "integrations": set(),
    "types": {"artifactr.ui._common", "artifactr.ui._html", "artifactr.ui.schema"},
    "wire": {"artifactr.ui.types", "artifactr.ui.checks", "artifactr.ui.integrations"},
    "checks": {
        "artifactr.ui._common",
        "artifactr.ui.ids",
        "artifactr.ui.integrations",
        "artifactr.ui.types",
    },
    "agent": {
        "artifactr.ui._common",
        "artifactr.ui.integrations",
        "artifactr.ui.schema",
        "artifactr.ui.types",
    },
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


@pytest.mark.parametrize("module", sorted(MODULES))
def test_a_module_imports_only_what_it_may(module: str) -> None:
    for name, imported in _imports(UI / f"{module}.py"):
        where = f"ui/{module} imports {name}"
        if _within(name, {"artifactr.ui"}):
            assert _within(name, MODULES[module]), f"{where}: not below it"
        elif name.split(".")[0] == "artifactr":
            assert name in PUBLIC, f"{where}: not one of artifactr's public modules"
            exported = importlib.import_module(name).__all__
            assert imported in exported, f"{where}.{imported}: not the layer's public API"


def test_every_module_has_its_layer() -> None:
    assert {path.stem for path in UI.glob("*.py")} == set(MODULES)


def test_nothing_else_in_artifactr_imports_it() -> None:
    importers = [
        path.relative_to(SRC)
        for path in SRC.rglob("*.py")
        if not path.is_relative_to(UI)
        and any(_within(name, {"artifactr.ui"}) for name, _ in _imports(path))
    ]
    assert importers == []
