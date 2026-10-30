# AGENTS.md: reflexr

Root [AGENTS.md](../../AGENTS.md) applies; this adds what is specific to reflexr.

reflexr runs rules over each workspace's event log and, when one fires, runs a workflow: a pydantic-ai agent, a pydantic-graph graph or an async function. Rules are typed data evaluated as pure reducers, so the same log always makes the same decisions. It is artifactr's sibling: they share conventions and neither imports the other. Design: [docs/reflexr/architecture.md](../../docs/reflexr/architecture.md); keep it current in the same PR as the code.

## Layout

| Path | What it is |
|---|---|
| `src/reflexr/core/` | Events, envelopes, conditions and their reducers, rules, the run lifecycle: pure, synchronous, no I/O |
| `src/reflexr/telemetry/` | Attribute names, the metric registry, tracer and instruments; never configures the SDK |
| `src/reflexr/workspace/` | `Workspaces`, the storage protocol, in-memory storage, the `Reactor`, function actions |
| `src/reflexr/agent/` | Agent and graph actions, `function_model` for tests |
| `src/reflexr/sql/` | `SqlStorage` and its packaged Alembic migrations (`sql/migrations/versions/`) |
| `src/reflexr/{fastapi,mcp,otel,langfuse,litellm,evals,scores}/` | Adapters behind extras |
| `tests/` | Mirrors `src/`; `conformance/cases/` holds the core's fixtures; `event_types.py`, `clock.py`, `databases.py` are shared helpers |
| `schemas/` | Generated rule and protocol JSON Schemas, and the OpenAPI document |
| `deploy/grafana/dashboards/` | Generated Grafana dashboards (`scripts/grafana_dashboards.py`) |
| `bruno/` | The acceptance collection that `reflexr:api` runs against `examples/oncall` |
| `compose.yaml`, `compose.stackr.yaml` | PostgreSQL for the tests, and oncall under the `app` profile |

## Tasks

Inherited: `lint`, `typecheck`, `test`, `format`, `check`, plus `build`, `standalone`, `deptry` (tag `distribution`) and `api` (tag `api`). Its own, from `moon.yml`:

```bash
moon run reflexr:schema       # regenerate everything in schemas/
moon run reflexr:dashboards   # regenerate deploy/grafana/dashboards/
moon run reflexr:pg-up        # PostgreSQL, as a compose project of its own on a free port
moon run reflexr:test-pg      # the tests on SQLite and PostgreSQL (after pg-up)
moon run reflexr:pg-down      # stop PostgreSQL, and oncall if it runs
moon run reflexr:app-up       # oncall on PostgreSQL at http://localhost:8000
moon run reflexr:api          # oncall, then Bruno and Schemathesis against it
```

A focused run is `uv run pytest packages/reflexr/tests/<path>.py -n0`.

## Tests

- PostgreSQL tests carry `@pytest.mark.postgres` and are deselected unless `REFLEXR_TEST_POSTGRES_URL` is set. Run `pg-up`, then `test-pg`. A cached `reflexr:test` won't rerun for the variable; pass `--force`.
- SQL tests take a backend from `tests/databases.py` (`SQL_BACKENDS`, `ROW_LEVEL_SECURITY`); each test gets its own schema. SQLite alone must reach 100% coverage.
- One behaviour suite runs against every storage; a new storage behaviour goes there, not in one backend's tests.
- Register test event types in `tests/event_types.py`. Use the fake clock in `tests/clock.py`, never sleep for time-based conditions.
- No test calls a model API: use `function_model` or pydantic-ai's `TestModel`.

## Layering

`tests/test_layering.py` lists, per layer, the reflexr layers and third-party modules it may import, and holds `examples/oncall` to the public API. Every outside dependency sits behind a port owned by the layer that needs it ([ADR-0025](../../docs/reflexr/adr/0025-ports-and-adapters.md)):

- `core` imports only pydantic and `lattice_core.schema`.
- Only `otel` imports the OpenTelemetry SDK; only `sql` imports SQLAlchemy and Alembic.
- reflexr never imports artifactr. A new third-party import goes into `LAYERS`, the matching extra in `pyproject.toml`, and the architecture table together.

## Generated files

- `schemas/*.json` come from `reflexr:schema`; `tests/test_openapi.py` and `tests/core/test_schema.py` fail on drift. Rerun after changing a rule, condition, protocol model or router.
- Dashboards come from `reflexr:dashboards` ([ADR-0038](../../docs/reflexr/adr/0038-dashboards-generated-tested-and-released.md)); `tests/test_dashboards.py` checks them against the metric registry.
- Migrations are hand-written, numbered `NNNN_name.py`; a test checks they build exactly the models' schema. Never edit a released one; add one.

## Pitfalls

- Rule evaluation must stay deterministic: firing ids are derived, not random (`core/ids.py`), so evaluating the same log twice produces the same firings.
- Runs execute at least once under leases; actions must be idempotent by their key ([ADR-0041](../../docs/reflexr/adr/0041-executing-runs.md), [ADR-0047](../../docs/reflexr/adr/0047-commands-carried-out-once-per-id.md)).
- Storage calls must be cancel-safe ([ADR-0042](../../docs/reflexr/adr/0042-cancel-safe-storage.md)).
- Text with a NUL character is refused at the boundary, since PostgreSQL can't store it ([ADR-0060](../../docs/reflexr/adr/0060-a-nul-character-is-refused-at-the-boundary.md)).
- Rule and event type names are qualified by namespace ([ADR-0039](../../docs/reflexr/adr/0039-namespaced-event-types.md), [ADR-0051](../../docs/reflexr/adr/0051-qualified-rule-names.md)).

## Key decisions

- [ADR-0013](../../docs/reflexr/adr/0013-quality-gates.md): quality gates
- [ADR-0030](../../docs/reflexr/adr/0030-sql-storage.md): SQL storage; [ADR-0062](../../docs/reflexr/adr/0062-row-level-security-under-the-scoping.md): row-level security
- [ADR-0040](../../docs/reflexr/adr/0040-telemetry-that-composes-across-libraries.md): telemetry that composes
- [ADR-0045](../../docs/reflexr/adr/0045-scores-on-evalr.md): scores on evalr
- [ADR-0021](../../docs/reflexr/adr/0021-contributor-compose-and-dev-containers.md), [ADR-0037](../../docs/reflexr/adr/0037-joining-stackrs-network.md): compose and stackr's network
