"""lattice-core's shipped code imports only the standard library and pydantic, never a lattice
package (lattice ADR-0018). An extra's module or subpackage may import what its extra installs,
and only it may import that module, so lattice-core imports without any extra installed."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

SOURCE = Path(__file__).parent.parent / "src" / "lattice_core"
EXTRAS = {
    "sql": {"sqlalchemy"},
    # The instrumentations import FastAPI and SQLAlchemy only when they are installed.
    "otel": {"opentelemetry", "pydantic_ai", "fastapi", "sqlalchemy", "langfuse"},
    "langfuse": {"langfuse", "opentelemetry"},
    "litellm": {"pydantic_ai", "httpx2"},
}
"""What each extra's module or subpackage may import beyond the standard library and pydantic."""

ALSO: dict[str, set[str]] = {"otel": {"langfuse"}}
"""The other extras' modules an extra's may import: ``configure_telemetry(langfuse=...)``
imports the ``langfuse`` extra's filters, which it needs only then."""


def _imports(path: Path) -> set[str]:
    """Every module a file imports, by its full name."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


@pytest.mark.parametrize(
    "path", sorted(SOURCE.rglob("*.py")), ids=lambda path: str(path.relative_to(SOURCE))
)
def test_shipped_code_imports_only_what_its_extra_installs(path: Path) -> None:
    extra = Path(path.relative_to(SOURCE).parts[0]).stem
    allowed = {"pydantic", *EXTRAS.get(extra, set())}
    reachable = {extra, *ALSO.get(extra, set())}
    for name in _imports(path):
        top = name.partition(".")[0]
        if top == "lattice_core":
            inside = name.split(".")[1:2]
            assert not inside or inside[0] not in EXTRAS or inside[0] in reachable, (
                f"{path.name} imports {name}, which needs an extra it doesn't"
            )
        else:
            assert top in sys.stdlib_module_names or top in allowed, f"{path.name} imports {name}"


def test_lattice_core_imports_without_its_extras() -> None:
    modules = sorted({module for extra in EXTRAS.values() for module in extra})
    blocked = "; ".join(f"sys.modules[{module!r}] = None" for module in modules)
    code = f"import sys; {blocked}; import lattice_core, lattice_core.schema, lattice_core.text"
    subprocess.run([sys.executable, "-c", code], check=True)
