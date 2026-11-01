"""lattice-core's shipped code imports only the standard library and pydantic, never a lattice
package (lattice ADR-0018). An extra's module or subpackage may import what its extra installs,
and only it may import that module, so lattice-core imports without any extra installed."""

import ast
import importlib.util
import pkgutil
import subprocess
import sys
from pathlib import Path

import pytest

import lattice_core

EXTRAS = {
    "sql": {"sqlalchemy"},
    "otel": {"opentelemetry", "pydantic_ai"},
    "langfuse": {"langfuse", "opentelemetry"},
    "litellm": {"pydantic_ai", "httpx2", "opentelemetry"},
    "agents": {"pydantic_ai"},
}
"""What each extra's module or subpackage may import beyond the standard library and pydantic."""

LAZY: dict[str, set[str]] = {
    # The instrumentations import FastAPI and SQLAlchemy only when they are installed, and the
    # Langfuse client only for configure_telemetry(langfuse=...).
    "lattice_core.otel.configure": {"fastapi", "sqlalchemy", "langfuse", "lattice_core.langfuse"},
    # The contract names the SDK's types in its annotations alone.
    "lattice_core.otel.contribution": {"opentelemetry"},
}
"""What each module may import only lazily: inside a function, or under ``TYPE_CHECKING``."""

BASE = {"lattice_core.otel", "lattice_core.otel.contribution"}
"""The modules inside an extra's subpackage that need no extra (lattice ADR-0020)."""

INSTALLS = {
    "sql": {"sqlalchemy"},
    "otel": {"opentelemetry.sdk", "opentelemetry.exporter", "opentelemetry.instrumentation"},
    # Langfuse brings the SDK and the OTLP exporter.
    "langfuse": {"langfuse", "opentelemetry.sdk", "opentelemetry.exporter"},
    "litellm": {"openai"},
    # pydantic-ai, which otel and litellm install too.
    "agents": set(),
}
"""What each extra installs that another may not: blocked while the others' modules import.
pydantic-ai brings httpx2 and OpenTelemetry's API, so those are never blocked for an extra."""

UNINSTALLED = {"fastapi", "asyncpg"}
"""What no extra installs: the application's own choice."""


def _extra(module: str) -> str | None:
    """The extra a module needs, or None."""
    inside = module.split(".")[1:2]
    return inside[0] if inside and inside[0] in EXTRAS and module not in BASE else None


MODULES = {"lattice_core": None} | {
    info.name: _extra(info.name)
    for info in pkgutil.walk_packages(lattice_core.__path__, "lattice_core.")
}
"""Every shipped module, and the extra it needs."""


def _imports(tree: ast.AST, *, lazy: bool = False) -> set[tuple[str, bool]]:
    """Every module a file imports, by its full name, and whether it imports it lazily."""
    found: set[tuple[str, bool]] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            found.update((alias.name, lazy) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add((node.module, lazy))
        else:
            deferred = isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) or (
                isinstance(node, ast.If) and ast.unparse(node.test) == "TYPE_CHECKING"
            )
            found |= _imports(node, lazy=lazy or deferred)
    return found


def _source(module: str) -> ast.AST:
    spec = importlib.util.find_spec(module)
    assert spec is not None
    assert spec.origin is not None
    return ast.parse(Path(spec.origin).read_text())


def _within(name: str, prefixes: set[str]) -> bool:
    return any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes)


def test_the_modules_that_need_no_extra_are_found() -> None:
    base = {module for module, extra in MODULES.items() if extra is None}
    assert base >= {
        "lattice_core.adapters",
        "lattice_core.approvals",
        "lattice_core.bindings",
        "lattice_core.capabilities",
        "lattice_core.egress",
        "lattice_core.enforcement",
        "lattice_core.logs",
        "lattice_core.otel.contribution",
        "lattice_core.schema",
        "lattice_core.secrets",
        "lattice_core.taint",
    }


@pytest.mark.parametrize("module", sorted(MODULES))
def test_shipped_code_imports_only_what_its_extra_installs(module: str) -> None:
    extra = MODULES[module]
    eager, lazy = {"pydantic", *EXTRAS.get(extra or "", ())}, LAZY.get(module, set())
    for name, deferred in _imports(_source(module)):
        where = f"{module} imports {name}"
        if _within(name, lazy):
            assert deferred, f"{where}, which it may import only lazily"
        elif name.partition(".")[0] == "lattice_core":
            assert _extra(name) in {None, extra}, f"{where}, which needs an extra it doesn't"
        else:
            assert name.partition(".")[0] in sys.stdlib_module_names or _within(name, eager), where


def _imported_without(modules: list[str], blocked: set[str]) -> None:
    """Import the modules in a fresh interpreter, with the blocked packages missing."""
    block = "; ".join(f"sys.modules[{name!r}] = None" for name in sorted(blocked))
    imports = "; ".join(f"import {module}" for module in modules)
    subprocess.run([sys.executable, "-c", f"import sys; {block}; {imports}"], check=True)


def test_lattice_core_imports_without_its_extras() -> None:
    every = {"opentelemetry", "pydantic_ai", *UNINSTALLED, *set().union(*INSTALLS.values())}
    _imported_without(sorted(m for m, extra in MODULES.items() if extra is None), every)


@pytest.mark.parametrize("extra", sorted(EXTRAS))
def test_each_extra_imports_without_the_others(extra: str) -> None:
    others = set[str]().union(*(INSTALLS[other] for other in EXTRAS if other != extra))
    modules = sorted(module for module, needs in MODULES.items() if needs == extra)
    _imported_without(modules, (others | UNINSTALLED) - INSTALLS[extra])
