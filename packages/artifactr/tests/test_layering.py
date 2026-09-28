"""The package layering in docs/architecture.md, enforced.

Each layer may import the standard library, the artifactr layers below it, and an explicit list
of third-party packages. Dependencies point one way, so each layer is usable without the ones
above it.
"""

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src" / "artifactr"
EXAMPLE = ROOT / "examples" / "docplan" / "src" / "docplan"

LAYERS: dict[str, tuple[set[str], set[str]]] = {
    # layer: (artifactr packages it may import, third-party packages it may import)
    "core": ({"artifactr.core"}, {"pydantic", "jsonpatch", "jsonpointer"}),
    "workspace": ({"artifactr.core", "artifactr.workspace"}, set()),
    "agent": (
        {"artifactr.core", "artifactr.workspace", "artifactr.agent"},
        {"pydantic", "pydantic_ai"},
    ),
    "fastapi": (
        {"artifactr.core", "artifactr.workspace", "artifactr.agent", "artifactr.fastapi"},
        {"fastapi", "starlette", "pydantic"},
    ),
    "mcp": (
        {"artifactr.core", "artifactr.workspace", "artifactr.agent", "artifactr.mcp"},
        {"mcp", "starlette", "pydantic"},
    ),
}


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


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
                continue
            if root == "artifactr":
                assert any(name == p or name.startswith(f"{p}.") for p in own), f"{where}: above"
            else:
                assert root in third_party, f"{where}: not a dependency of this layer"


PUBLIC = {"artifactr", *(f"artifactr.{package}" for package in (*LAYERS, "sql"))}


def test_the_reference_implementation_uses_only_the_public_api() -> None:
    modules = sorted(EXAMPLE.rglob("*.py"))
    assert modules, "the reference implementation has no modules"
    for path in modules:
        for name in _imports(path):
            if name.split(".")[0] == "artifactr":
                assert name in PUBLIC, f"{path.relative_to(ROOT)} imports {name}, not a package"
