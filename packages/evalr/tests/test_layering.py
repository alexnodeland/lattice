"""The package layering in docs/architecture.md, enforced.

Each package may import the standard library, the evalr packages below it, and an explicit list of
third-party packages. Dependencies point one way, so each package is usable without the others,
and evalr never imports artifactr or reflexr.
"""

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src" / "evalr"

LAYERS: dict[str, tuple[set[str], set[str]]] = {
    # package: (evalr packages it may import, third-party packages it may import)
    "core": ({"evalr.core"}, {"pydantic", "annotated_types", "opentelemetry"}),
    "memory": ({"evalr.core", "evalr.memory"}, {"pydantic"}),
    "contracts": ({"evalr.core", "evalr.contracts"}, {"pydantic"}),
    "jsonl": ({"evalr.core", "evalr.jsonl"}, {"pydantic"}),
}

FORBIDDEN = {"artifactr", "reflexr"}


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
            if root == "evalr":
                assert any(name == p or name.startswith(f"{p}.") for p in own), f"{where}: above"
            else:
                assert root in third_party, f"{where}: not a dependency of this layer"


def test_every_package_has_a_layer() -> None:
    packages = {p.name for p in SRC.iterdir() if (p / "__init__.py").exists()}
    assert packages == set(LAYERS)


@pytest.mark.parametrize("layer", sorted(set(LAYERS) - {"core"}))
def test_adapters_depend_inward_only(layer: str) -> None:
    own, _ = LAYERS[layer]
    assert own == {"evalr.core", f"evalr.{layer}"}


def test_nothing_imports_the_libraries_that_depend_on_evalr() -> None:
    for path in sorted(SRC.rglob("*.py")):
        roots = {name.split(".")[0] for name in _imports(path)}
        assert not roots & FORBIDDEN, f"{path.relative_to(SRC)} imports {roots & FORBIDDEN}"
