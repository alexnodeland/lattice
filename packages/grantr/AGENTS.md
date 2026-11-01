# AGENTS.md: grantr

Root [AGENTS.md](../../AGENTS.md) applies; this adds what is specific to grantr.

grantr is identity and access for artifactr, reflexr and portalr: tenants, members, groups, roles, service principals, and grants on tenants, workspaces, threads, artifacts and rules. The libraries ask it, through their own hooks, before every command and read. See [the architecture](../../docs/grantr/architecture.md).

## Layout

- `src/grantr/core/`: the model and the decisions. Pure: no I/O.
- `src/grantr/grants/`: `Grants`, the commands and checks over the storage port, and the audit log.
- `src/grantr/sql/`: the SQL storage adapter and its Alembic migrations, with row-level security (`sql`, `sqlite`, `postgres` extras).
- `src/grantr/fastapi/`: the admin router and its OpenAPI document (`fastapi` extra).
- `src/grantr/telemetry/`, `testing/`: metrics and spans; test helpers for applications.
- `schemas/grantr.openapi.json`: generated.

## Commands

```bash
moon run grantr:test          # SQLite and memory; PostgreSQL tests deselected
moon run grantr:check
moon run grantr:schema        # regenerate schemas/grantr.openapi.json
moon run grantr:pg-up         # PostgreSQL from compose.yaml, on a free port
moon run grantr:test-pg       # the tests on PostgreSQL as well (after pg-up)
moon run grantr:pg-down
uv run pytest packages/grantr/tests/grants -n0
```

`test` runs with `--numprocesses auto`. `test-pg` sets `GRANTR_TEST_POSTGRES_URL`; without it, tests marked `postgres` are deselected (and counted). After a cached `test`, use `moon run grantr:test --force`.

## Generated files

`tests/test_schema.py` fails when `schemas/grantr.openapi.json` differs from the router. Change a route, then run `moon run grantr:schema`, then `moon run client:types` for portalr's client.

## Layering

`tests/test_layering.py` enforces it:

- `core` imports pydantic and `lattice_core.settings` only, and no I/O modules of the standard library (`asyncio`, `os`, `pathlib`, `logging`, `sqlite3`, ...).
- `grants` imports `core`, `telemetry`, the OpenTelemetry API and `lattice_core.integrations`/`settings`/`approvals`/`capabilities`/`enforcement`.
- `sql` and `fastapi` import `core` (and `fastapi` also `grants`, `sql` also `lattice_core.sql`/`approvals`), never each other.
- grantr imports no sibling but lattice-core: never artifactr, reflexr or portalr. Their types reach it structurally; action catalogs are passed in.
- A new package under `src/grantr/` needs an entry in `LAYERS`.

## Conventions

- Checks deny by default and write nothing ([ADR-0015](../../docs/grantr/adr/0015-a-check-writes-nothing.md)).
- Every change to access is recorded in the append-only audit log ([ADR-0007](../../docs/grantr/adr/0007-an-append-only-audit-log.md)), in the same transaction ([ADR-0013](../../docs/grantr/adr/0013-transactions-by-tenant-and-one-audit-log.md)).
- A command can't grant more than its maker holds ([ADR-0010](../../docs/grantr/adr/0010-commands-bounded-by-what-their-maker-holds.md)).
- A schema change is a new Alembic migration in `src/grantr/sql/`; don't edit a released one.
- Storage behaviour is tested on memory, SQLite and PostgreSQL alike; use the fixtures in `tests/databases.py`.

## Key ADRs

- [ADR-0001](../../docs/grantr/adr/0001-the-hook-hears-the-action.md): the hook hears the action.
- [ADR-0008](../../docs/grantr/adr/0008-grantrs-own-model-with-openfga-shaped-ports.md): its own model, OpenFGA-shaped ports.
- [ADR-0016](../../docs/grantr/adr/0016-the-sql-adapter.md), [ADR-0017](../../docs/grantr/adr/0017-the-admin-api.md): the SQL adapter, the admin API.
- [ADR-0026](../../docs/grantr/adr/0026-row-level-security-under-the-scoping.md): row-level security.
- [ADR-0028](../../docs/grantr/adr/0028-a-principals-id-cant-pass-for-the-libraries-actors.md): a principal's id can't pass for the libraries' actors.

## Pitfalls

- This is security code: a new branch that allows something needs a test that it denies otherwise.
- Row-level security is only exercised on PostgreSQL; run `test-pg` for any change to `sql/`.
