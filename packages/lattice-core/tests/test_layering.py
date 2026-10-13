"""lattice-core's shipped code imports only the standard library and pydantic, never a lattice
package (lattice ADR-0018)."""

import ast
import sys
from pathlib import Path

import pytest

SOURCE = Path(__file__).parent.parent / "src" / "lattice_core"
ALLOWED = {"lattice_core", "pydantic"}
"""The modules beyond the standard library that lattice-core may import: its own and pydantic."""


def _imports(path: Path) -> set[str]:
    """The top-level names of the modules a file imports."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.partition(".")[0])
    return names


@pytest.mark.parametrize("path", sorted(SOURCE.rglob("*.py")), ids=lambda p: p.name)
def test_shipped_code_imports_only_the_standard_library_and_pydantic(path: Path) -> None:
    outside = _imports(path) - sys.stdlib_module_names - ALLOWED
    assert not outside, f"{path.name} imports {sorted(outside)}"
