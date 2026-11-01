"""The package layering in <https://lattice.alexnodeland.com/reflexr/architecture/>, enforced.

Each layer may import the standard library, the reflexr layers below it, and an explicit list of
third-party modules. Dependencies point one way, so each layer is usable without the ones above.
"""

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src" / "reflexr"

LAYERS: dict[str, tuple[set[str], set[str]]] = {
    # layer: (reflexr packages it may import, third-party packages it may import)
    # lattice-core's helpers, shared with artifactr (lattice ADR-0018).
    "core": ({"reflexr.core"}, {"pydantic", "pydantic_core", "lattice_core.schema"}),
    # The telemetry contract's MetricsDetail, which needs no extra (lattice ADR-0020).
    "telemetry": (
        {"reflexr.core", "reflexr.telemetry"},
        {"opentelemetry", "lattice_core.otel.contribution"},
    ),
    "workspace": (
        {"reflexr.core", "reflexr.telemetry", "reflexr.workspace"},
        {"pydantic", "opentelemetry", "cronsim", "lattice_core.text"},
    ),
    "fastapi": (
        {"reflexr.core", "reflexr.telemetry", "reflexr.workspace", "reflexr.fastapi"},
        {"pydantic", "opentelemetry", "fastapi", "starlette", "lattice_core.refusals"},
    ),
    "mcp": (
        {"reflexr.core", "reflexr.telemetry", "reflexr.workspace", "reflexr.mcp"},
        {"pydantic", "opentelemetry", "mcp", "starlette", "lattice_core.logs"},
    ),
    # The feedback mirror, on evalr's score mapping and ports (ADR-0045).
    "scores": (
        {"reflexr.core", "reflexr.telemetry", "reflexr.workspace", "reflexr.scores"},
        {"pydantic", "evalr.core"},
    ),
    # The evalr adapter. Only it, and the mirror through evalr.core, may import evalr.
    "evals": (
        {"reflexr.core", "reflexr.telemetry", "reflexr.workspace", "reflexr.evals"},
        {"pydantic", "evalr"},
    ),
    # The OpenTelemetry SDK adapter, on lattice-core's; it names SQLAlchemy's engines only in
    # its annotations.
    "otel": (
        {"reflexr.telemetry", "reflexr.otel"},
        {"opentelemetry", "sqlalchemy", "lattice_core.otel"},
    ),
    "langfuse": (
        {"reflexr.core", "reflexr.telemetry", "reflexr.workspace", "reflexr.langfuse"},
        {"langfuse", "opentelemetry", "lattice_core.langfuse"},
    ),
    "litellm": (
        {"reflexr.core", "reflexr.telemetry", "reflexr.workspace", "reflexr.litellm"},
        {"pydantic_ai", "opentelemetry", "lattice_core.litellm", "lattice_core.tags"},
    ),
    "agent": (
        {"reflexr.core", "reflexr.telemetry", "reflexr.workspace", "reflexr.agent"},
        {"pydantic", "pydantic_core", "opentelemetry", "pydantic_ai", "pydantic_graph"},
    ),
    "sql": (
        {"reflexr.core", "reflexr.telemetry", "reflexr.workspace", "reflexr.sql"},
        {"pydantic", "sqlalchemy", "alembic", "lattice_core.sql"},
    ),
    # reflexr's static catalog (lattice RFC-0014): commands declared on lattice-core's types and
    # core's models, reading nothing, so the parity test and the schema read it without a
    # workspace; and its provider, which opens one for each call (ADR-0068).
    "commands": (
        {"reflexr.core", "reflexr.workspace", "reflexr.commands"},
        {"pydantic", "lattice_core.capabilities", "lattice_core.commands"},
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
            if root == "reflexr":
                assert _within(name, own), f"{where}: above"
            else:
                assert _within(name, third_party), f"{where}: not a dependency of this layer"


EXAMPLE = Path(__file__).parents[3] / "examples" / "oncall" / "src" / "oncall"
PUBLIC = {"reflexr", *(f"reflexr.{layer}" for layer in LAYERS)}
"""What an application imports from: reflexr and its packages, never the modules inside them."""


def test_the_reference_implementation_uses_only_the_public_api() -> None:
    modules = sorted(EXAMPLE.rglob("*.py"))
    assert modules, "the reference implementation has no modules"
    for path in modules:
        for name in _imports(path):
            if name.split(".")[0] == "reflexr":
                where = f"{path.name} imports {name}, not a package's public name"
                assert _within(name, PUBLIC), where
                assert name.count(".") <= 2, where
