# AGENTS.md: artifactr

Root [AGENTS.md](../../AGENTS.md) applies; this adds what is specific to artifactr.

artifactr is a library for chat applications in which people and agents edit the same versioned, attributed artifacts; agents propose, people accept. It is distributed as **`artifactr-ai`** and imported as `artifactr`. Its design is [docs/artifactr/architecture.md](../../docs/artifactr/architecture.md); keep it current in the same PR as the code.

## Layout

| Path | What it is |
|---|---|
| `src/artifactr/core/` | Every rule: pure, synchronous, no I/O, no pydantic-ai, no OpenTelemetry |
| `src/artifactr/telemetry/`, `workspace/`, `agent/` | The other inner layers: OpenTelemetry API, the `Storage` port and handles, the pydantic-ai capability and `Runner` |
| `src/artifactr/sql/` | SQLAlchemy storage and its packaged Alembic migrations (`sql/migrations/versions/`) |
| `src/artifactr/{fastapi,mcp,otel,langfuse,litellm,evals,scores}/` | Adapters behind extras |
| `src/artifactr/files/` | Native files, a domain built on artifactr with its own rules ([its AGENTS.md](src/artifactr/files/AGENTS.md)) |
| `src/artifactr/{ui,excalidraw,connect}/` | Forms and dashboards, diagrams, connected apps |
| `src/artifactr/capabilities/` | The artifact tools as capabilities for lattice-core's registry, each called through its enforcer ([ADR-0099](../../docs/artifactr/adr/0099-artifactrs-tools-as-capabilities-called-through-the-enforcer-whose-policy-asks-approval.md)) |
| `tests/` | Mirrors `src/`; `conformance/` holds the protocol fixtures |
| `schemas/` | Generated JSON Schemas and OpenAPI documents |
| `deploy/grafana/dashboards/` | Generated Grafana dashboards (`scripts/grafana_dashboards.py`) |
| `bruno/` | The acceptance collection that `artifactr:api` runs against docplan |
| `typings/` | Stubs for untyped dependencies (jsonpatch, jsonpointer, dspy) |
| `compose.yaml`, `compose.stackr.yaml` | PostgreSQL for the tests, and docplan under the `app` profile |

## Tasks

Inherited: `lint`, `typecheck`, `test`, `format`, `check`, plus `build`, `standalone`, `deptry` (tag `distribution`) and `api` (tag `api`). Its own, from `moon.yml`:

```bash
moon run artifactr:schema       # regenerate everything in schemas/
moon run artifactr:dashboards   # regenerate deploy/grafana/dashboards/
moon run artifactr:pg-up        # PostgreSQL, as a compose project of its own on a free port
moon run artifactr:test-pg      # the tests on SQLite and PostgreSQL (after pg-up)
moon run artifactr:pg-down      # stop PostgreSQL, and docplan if it runs
moon run artifactr:app-up       # docplan on PostgreSQL at http://localhost:8000
moon run artifactr:api          # docplan, then Bruno and Schemathesis against it
moon run artifactr:spec         # TLC over docs/artifactr/spec/ThreadClaim.tla (needs Java 11+)
moon run artifactr:spec-deep    # the same at Nightly's bounds
CRAFT=wordcraft moon run artifactr:fidelity   # a crafting app's live fidelity report
```

`test` runs with `--numprocesses auto`; a focused run is `uv run pytest packages/artifactr/tests/<path>.py -n0`.

## Tests

- PostgreSQL tests carry `@pytest.mark.postgres` and are deselected unless `ARTIFACTR_TEST_POSTGRES_URL` is set. Run `pg-up`, then `test-pg`. A cached `artifactr:test` won't rerun for the variable; pass `--force`.
- SQL tests take a backend from `tests/databases.py` (`SQL_BACKENDS`, `ROW_LEVEL_SECURITY`); each test gets its own schema. SQLite alone must reach 100% coverage.
- `@pytest.mark.craft(app)` tests need a crafting app's CLI (`ARTIFACTR_TEST_CRAFT`, `ARTIFACTR_TEST_CRAFT_CLI`); use the `fidelity` task, not hand-set variables.
- `tests/conftest.py` fails an async test that leaves a task running, and a `TestClient` used outside `with`. Cancel what you start; enter clients.
- Register test artifact types in `tests/artifact_types.py`, not in test modules.
- No test calls a model API: use pydantic-ai's `TestModel` or `function_model`.

## Layering

`tests/test_layering.py` lists, per layer, the artifactr layers and third-party modules it may import, and holds `examples/docplan` to the public API. Dependencies point inward ([ADR-0034](../../docs/artifactr/adr/0034-ports-and-adapters-for-integrations.md)):

- Inner layers (`core`, `telemetry`, `workspace`, `agent`) reach OpenTelemetry through the API only; only `otel` imports the SDK.
- An adapter imports its extra's libraries and the inner layers, never the reverse.
- artifactr never imports reflexr. A new third-party import goes into `LAYERS`, the matching extra in `pyproject.toml`, and the architecture table together.

## Generated files

- `schemas/*.json` come from `artifactr:schema`; `tests/test_schema.py` and `tests/test_openapi.py` fail on drift. Rerun after changing any protocol model, router or wire type.
- Dashboards come from `artifactr:dashboards`; `tests/test_dashboards.py` checks each query against the metric registry. Add a metric to the registry first.
- Migrations are hand-written, numbered `NNNN_name.py` in `sql/migrations/versions/`; a test checks they build exactly the models' schema. Never edit a released migration; add one.

## Pitfalls

- The PyPI name `artifactr` is someone else's; dependencies say `artifactr-ai`.
- `spec` takes the agent, workspace, `sql/storage.py` and `core/rules.py` as inputs: a change to the thread claim must keep [the TLA+ spec](../../docs/artifactr/spec/) true.
- `bruno/` requests run in order against docplan's `acceptance` workspace; a changed REST route needs its `.bru` updated and `artifactr:api` passing.

## Key decisions

- [ADR-0034](../../docs/artifactr/adr/0034-ports-and-adapters-for-integrations.md): ports and adapters
- [ADR-0046](../../docs/artifactr/adr/0046-telemetry-that-composes-across-libraries.md): telemetry that composes
- [ADR-0049](../../docs/artifactr/adr/0049-scores-on-evalr.md): scores on evalr
- [ADR-0030](../../docs/artifactr/adr/0030-compose-and-dev-containers.md), [ADR-0040](../../docs/artifactr/adr/0040-joining-stackrs-network.md): compose and stackr's network
- [ADR-0074](../../docs/artifactr/adr/0074-forms-and-dashboards-in-artifactr-ui-behind-the-forms-extra.md), [ADR-0090](../../docs/artifactr/adr/0090-diagrams-drawn-by-the-agent-through-a-converter.md): forms, diagrams
- [lattice ADR-0025](../../docs/adr/0025-formal-specs-in-tla-and-lean.md): formal specs
