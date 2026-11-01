"""The layering in portr's architecture, enforced (lattice RFC-0014, Decision O7).

portr reaches the libraries' commands only through lattice-core's registry: it never imports
artifactr, reflexr, evalr or relayr. The core imports no MCP SDK and does no I/O.
"""

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src" / "portr"

LIBRARIES = {"artifactr", "reflexr", "evalr", "relayr", "portalr"}
"""What portr never imports."""

LAYERS: dict[str, tuple[set[str], set[str]]] = {
    # layer: (portr packages it may import, third-party modules it may import)
    "core": ({"portr.core"}, {"pydantic", "lattice_core.capabilities", "lattice_core.commands"}),
}


def _imports(path: Path) -> set[str]:
    """Every module a file imports."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _within(name: str, prefixes: set[str]) -> bool:
    return any(name == p or name.startswith(f"{p}.") for p in prefixes)


@pytest.mark.parametrize("layer", sorted(LAYERS))
def test_layer_imports_only_what_it_may(layer: str) -> None:
    own, third_party = LAYERS[layer]
    modules = sorted((SRC / layer).rglob("*.py"))
    assert modules, f"layer {layer} has no modules"
    for path in modules:
        for module in _imports(path):
            root = module.split(".")[0]
            where = f"{path.relative_to(SRC)} imports {module}"
            if root in sys.stdlib_module_names:
                continue
            assert root not in LIBRARIES, f"{where}: portr imports no library"
            if root == "portr":
                assert _within(module, own), f"{where}: above"
            else:
                assert _within(module, third_party), f"{where}: not a dependency of this layer"


def test_every_package_is_a_layer() -> None:
    packages = {path.name for path in SRC.iterdir() if (path / "__init__.py").exists()}
    assert packages == set(LAYERS)
