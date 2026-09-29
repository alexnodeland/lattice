"""The package layering in docs/architecture.md, enforced.

Each layer may import the standard library, the artifactr layers below it, and an explicit list
of third-party modules. Dependencies point one way, so each layer is usable without the ones
above it.

Ports and adapters (ADR-0034): the inner layers reach OpenTelemetry through its API only, the
port; the SDK, exporters and instrumentations are adapters, and only the ``otel`` extra may
import them. Each extra imports its own third-party libraries plus the inner layers.
"""

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src" / "artifactr"
EXAMPLE = ROOT / "examples" / "docplan" / "src" / "docplan"

OTEL_API = {
    "opentelemetry.baggage",
    "opentelemetry.context",
    "opentelemetry.metrics",
    "opentelemetry.trace",
    "opentelemetry.util.types",
}
"""The OpenTelemetry API: the port every layer may record through."""

INNER = {"artifactr.core", "artifactr.telemetry", "artifactr.workspace", "artifactr.agent"}

LAYERS: dict[str, tuple[set[str], set[str]]] = {
    # layer: (artifactr packages it may import, third-party modules it may import)
    "core": ({"artifactr.core"}, {"pydantic", "jsonpatch", "jsonpointer"}),
    "telemetry": ({"artifactr.core", "artifactr.telemetry"}, OTEL_API),
    "workspace": ({"artifactr.core", "artifactr.telemetry", "artifactr.workspace"}, OTEL_API),
    "agent": (INNER, {"pydantic", "pydantic_ai", *OTEL_API}),
    "sql": ({"artifactr.core", "artifactr.workspace", "artifactr.sql"}, {"sqlalchemy", "alembic"}),
    # Feedback as scores: the mirror, on evalr's mapping and ports (ADR-0038).
    "scores": (
        {"artifactr.core", "artifactr.workspace", "artifactr.scores"},
        {"pydantic", "evalr.core"},
    ),
    "fastapi": (
        {*INNER, "artifactr.fastapi"},
        {"fastapi", "starlette", "pydantic", *OTEL_API},
    ),
    "mcp": ({*INNER, "artifactr.mcp"}, {"mcp", "starlette", "pydantic", *OTEL_API}),
    # The OpenTelemetry SDK adapter; it imports FastAPI and SQLAlchemy only to instrument them.
    "otel": (
        {"artifactr.core", "artifactr.telemetry", "artifactr.otel", "artifactr.langfuse"},
        {"opentelemetry", "pydantic_ai", "fastapi", "sqlalchemy", "langfuse"},
    ),
    # The LiteLLM adapter: a model over the proxy, and a capability for each request.
    "litellm": (
        {*INNER, "artifactr.litellm"},
        {"pydantic_ai", "httpx2", "opentelemetry.propagate", *OTEL_API},
    ),
    # The Langfuse adapter: evalr's score ports, a TurnContext and a span filter.
    "langfuse": (
        {*INNER, "artifactr.scores", "artifactr.langfuse"},
        {"langfuse", "opentelemetry", "evalr.core"},
    ),
    # The evalr adapter: a feedback source, experiment tasks, a TurnEvaluator and measures.
    # Only this layer, and the score mirror and its Langfuse adapter, may import evalr.
    "evals": (
        {*INNER, "artifactr.evals"},
        {"evalr", "pydantic", "pydantic_ai", *OTEL_API},
    ),
}


def _imports(path: Path) -> set[str]:
    """Every module a file imports, with ``from m import n`` counted as ``m.n``."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _within(name: str, prefixes: set[str]) -> bool:
    return any(name == p or name.startswith(f"{p}.") for p in prefixes)


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
                assert _within(name, own), f"{where}: above"
            else:
                assert _within(name, third_party), f"{where}: not a dependency of this layer"


def test_every_package_is_a_layer() -> None:
    packages = {path.name for path in SRC.iterdir() if (path / "__init__.py").exists()}
    assert packages == set(LAYERS)


PUBLIC = {"artifactr", *(f"artifactr.{package}" for package in LAYERS)}


def test_the_reference_implementation_uses_only_the_public_api() -> None:
    modules = sorted(EXAMPLE.rglob("*.py"))
    assert modules, "the reference implementation has no modules"
    for path in modules:
        for name in _imports(path):
            if name.split(".")[0] == "artifactr":
                where = f"{path.relative_to(ROOT)} imports {name}, not a package's public name"
                assert _within(name, PUBLIC), where
                assert name.count(".") <= 2, where
