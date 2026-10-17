"""The package layering in <https://lattice.alexnodeland.com/artifactr/architecture/>, enforced.

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
EXAMPLE = ROOT.parent.parent / "examples" / "docplan" / "src" / "docplan"

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
    # lattice-core's helpers, shared with reflexr (lattice ADR-0018).
    "core": ({"artifactr.core"}, {"pydantic", "jsonpatch", "jsonpointer", "lattice_core.schema"}),
    # The telemetry contract's MetricsDetail, which needs no extra (lattice ADR-0020).
    "telemetry": (
        {"artifactr.core", "artifactr.telemetry"},
        {"lattice_core.otel.contribution", *OTEL_API},
    ),
    "workspace": (
        {"artifactr.core", "artifactr.telemetry", "artifactr.workspace"},
        {"pydantic", "lattice_core.integrations", "lattice_core.text", *OTEL_API},
    ),
    "agent": (INNER, {"pydantic", "pydantic_ai", *OTEL_API}),
    "sql": (
        {"artifactr.core", "artifactr.workspace", "artifactr.sql"},
        {"sqlalchemy", "alembic", "lattice_core.sql"},
    ),
    # Feedback as scores: the mirror, on evalr's mapping and ports (ADR-0049).
    "scores": (
        {"artifactr.core", "artifactr.telemetry", "artifactr.workspace", "artifactr.scores"},
        {"pydantic", "evalr.core"},
    ),
    # The OpenAPI document's bare application gives its runner an agent, which never runs.
    "fastapi": (
        {*INNER, "artifactr.fastapi"},
        {
            "fastapi",
            "starlette",
            "pydantic",
            "pydantic_ai",
            "lattice_core.refusals",
            *OTEL_API,
        },
    ),
    "mcp": (
        {*INNER, "artifactr.mcp"},
        {"mcp", "starlette", "pydantic", "lattice_core.logs", *OTEL_API},
    ),
    # The OpenTelemetry SDK adapter, on lattice-core's; it names SQLAlchemy's engines only in
    # its annotations.
    "otel": (
        {"artifactr.telemetry", "artifactr.otel"},
        {"opentelemetry", "sqlalchemy", "lattice_core.otel"},
    ),
    # The LiteLLM adapter: a model over the proxy, and a capability for each request.
    "litellm": (
        {*INNER, "artifactr.litellm"},
        {
            "pydantic_ai",
            "opentelemetry.propagate",
            "lattice_core.litellm",
            "lattice_core.tags",
            *OTEL_API,
        },
    ),
    # The Langfuse adapter: a TurnContext, a span filter and the client. Scores are evalr's.
    "langfuse": (
        {*INNER, "artifactr.langfuse"},
        {"langfuse", "opentelemetry", "lattice_core.langfuse"},
    ),
    # The evalr adapter: a feedback source, experiment tasks, a TurnEvaluator and measures.
    # Only this layer and the score mirror may import evalr.
    "evals": (
        {*INNER, "artifactr.evals"},
        {"evalr", "pydantic", "pydantic_ai", *OTEL_API},
    ),
    # Native files, the files extra (lattice RFC-0003 and ADR-0026): built on the public API of
    # core and the workspace, with its SQL stores in the sql extra. tests/files/test_layering.py
    # holds its own layers.
    "files": (
        {"artifactr.core", "artifactr.workspace", "artifactr.files"},
        {"pydantic", "sqlalchemy", "alembic", "lattice_core.sql"},
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


def test_the_package_root_imports_only_the_inner_layers() -> None:
    for name in _imports(SRC / "__init__.py"):
        if name.split(".")[0] not in sys.stdlib_module_names:
            assert _within(name, INNER), name


PUBLIC = {"artifactr", *(f"artifactr.{package}" for package in LAYERS)}


def test_the_reference_implementation_uses_only_the_public_api() -> None:
    modules = sorted(EXAMPLE.rglob("*.py"))
    assert modules, "the reference implementation has no modules"
    for path in modules:
        for name in _imports(path):
            if name.split(".")[0] == "artifactr":
                where = f"{path.relative_to(EXAMPLE)} imports {name}, not a package's public name"
                assert _within(name, PUBLIC), where
                assert name.count(".") <= 2, where
