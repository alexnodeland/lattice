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
        {
            "pydantic",
            "lattice_core.integrations",
            "lattice_core.settings",
            "lattice_core.text",
            *OTEL_API,
        },
    ),
    "agent": (INNER, {"pydantic", "pydantic_ai", *OTEL_API}),
    "sql": (
        {"artifactr.core", "artifactr.workspace", "artifactr.sql"},
        # anyio shields the advisory lock's release from a cancellation (ADR-0085).
        {"sqlalchemy", "alembic", "anyio", "lattice_core.sql"},
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
    # Forms and dashboards, behind the forms extra (ADR-0074): a plugin nothing else imports.
    "ui": (
        {*INNER, "artifactr.ui"},
        {
            "pydantic",
            "pydantic_core",
            "pydantic_ai",
            "lattice_core.schema",
            "lattice_core.integrations",
        },
    ),
    # Excalidraw diagrams, the excalidraw extra (lattice RFC-0006): a plugin nothing else
    # imports, on core's, the workspace's and the agent's public API; its images in native files'
    # blob store, and its converter's worker over httpx (artifactr ADR-0090); and the routes a
    # canvas puts its images on, over artifactr's router's auth and native files' pace (ADR-0092).
    "excalidraw": (
        {
            *("artifactr.core", "artifactr.workspace", "artifactr.agent", "artifactr.excalidraw"),
            *("artifactr.files.blobs", "artifactr.files.native.pace"),
            *("artifactr.fastapi", "artifactr.telemetry"),
        },
        {
            *("pydantic", "pydantic_ai", "httpx", "anyio", "fastapi", "starlette"),
            *("lattice_core.integrations", "lattice_core.refusals"),
        },
    ),
    # The evalr adapter: a feedback source, experiment tasks, a TurnEvaluator and measures.
    # Only this layer and the score mirror may import evalr.
    "evals": (
        {*INNER, "artifactr.evals"},
        {"evalr", "pydantic", "pydantic_ai", *OTEL_API},
    ),
    # Connected apps, the connect extra (ADR-0085): the agent's tools for an operator's own app,
    # on the agent's and the workspace's public API, behind the switches and settings
    # lattice-core declares, over the MCP client the extra brings.
    "connect": (
        {*INNER, "artifactr.connect"},
        {
            *("pydantic_ai", "pydantic_core", "mcp", "anyio"),
            *("lattice_core.integrations", "lattice_core.settings", "lattice_core.capabilities"),
        },
    ),
    # artifactr's static catalog (lattice RFC-0014): commands declared on lattice-core's types,
    # reading nothing, so the parity test and the schema read it without a workspace.
    "commands": (
        {"artifactr.commands"},
        {"pydantic", "lattice_core.capabilities", "lattice_core.commands"},
    ),
    # artifactr's provider (lattice RFC-0011): its artifact tools as capabilities, on the agent's
    # and the workspace's public API, against lattice-core's capabilities contract.
    "capabilities": (
        {*INNER, "artifactr.capabilities"},
        {"pydantic", "lattice_core.capabilities"},
    ),
    # Native files, the files extra (lattice RFC-0003 and ADR-0026): built on the public API of
    # core and the workspace, with its SQL stores in the sql extra and the apps' adapters on the
    # MCP client the files extra brings, and the agent's tools on the agent's public API, behind
    # the switch lattice-core declares, and people's check-out over artifactr's router's auth.
    # The worker serves an app with Starlette and uvicorn, and the application calls it with
    # httpx. FreeCAD's script runs in FreeCAD's own interpreter, on its modules and the Pillow it
    # ships, and Blender's in Blender's, on its modules; Blender's scan inflates zstd.
    # tests/files/test_layering.py holds its own layers.
    "files": (
        {
            *("artifactr.core", "artifactr.workspace", "artifactr.agent", "artifactr.fastapi"),
            "artifactr.telemetry",
            "artifactr.files",
        },
        {
            *("pydantic", "pydantic_ai", "sqlalchemy", "alembic", "mcp", "anyio"),
            *("fastapi", "starlette", "uvicorn", "httpx"),
            *("lattice_core.sql", "lattice_core.integrations", "lattice_core.refusals"),
            "lattice_core.origins",
            *("FreeCAD", "Part", "Sketcher", "TechDraw", "PIL"),
            *("zstandard", "bpy", "bmesh", "mathutils"),
        },
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
# Native files' own optional surfaces, each a package's public name a level down.
PUBLIC_SURFACES = {"artifactr.files.fastapi"}


def test_the_reference_implementation_uses_only_the_public_api() -> None:
    modules = sorted(EXAMPLE.rglob("*.py"))
    assert modules, "the reference implementation has no modules"
    for path in modules:
        for name in _imports(path):
            if name.split(".")[0] == "artifactr":
                where = f"{path.relative_to(EXAMPLE)} imports {name}, not a package's public name"
                assert _within(name, PUBLIC), where
                surface = _within(name, PUBLIC_SURFACES)
                assert name.count(".") <= (3 if surface else 2), where
