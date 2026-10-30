# AGENTS.md: relayr

Root [AGENTS.md](../../AGENTS.md) applies; this adds what is specific to relayr.

relayr is the bridge between artifactr and reflexr: events from chats and artifacts become reflexr events, and runs act back in artifactr as proposals and notices. It also writes to task trackers (Plane, Vikunja). It is distributed as `relayr-ai` and imported as `relayr`. See [the architecture](../../docs/relayr/architecture.md).

## Layout

- `src/relayr/events/`: the bridged event types.
- `src/relayr/inbound/`, `outbound/`: the followers into reflexr, and the capability runs act through.
- `src/relayr/ledger/`, `sql/`: cursors, leases and dead letters, in memory or SQL (with Alembic migrations).
- `src/relayr/rules/`, `evals/`: rules from chat; proposal outcomes as feedback (`evals` extra).
- `src/relayr/trackers/`, `plane/`, `vikunja/`: the tracker port, its fake, and its adapters.
- `src/relayr/fastapi/`: webhook and connector routes, and the OpenAPI document.
- `src/relayr/telemetry/`, `otel/`, `langfuse/`, `integrations/`, `ui/`, `excalidraw/`: telemetry, extras, and the forms and diagram bridges.
- `schemas/relayr.openapi.json`: generated; portalr's client is typed from it.

## Commands

```bash
moon run relayr:test            # memory and SQLite; PostgreSQL tests deselected
moon run relayr:check
moon run relayr:schema          # regenerate schemas/relayr.openapi.json
moon run relayr:pg-up           # PostgreSQL from compose.yaml, on a free port
moon run relayr:test-pg         # the tests on PostgreSQL as well (after pg-up)
moon run relayr:vikunja-up      # Vikunja on port 54333 (compose profile `trackers`)
moon run relayr:test-vikunja    # the tracker contract test, live (after vikunja-up)
moon run relayr:pg-down         # stops PostgreSQL and Vikunja
uv run pytest packages/relayr/tests/inbound -n0
```

relayr depends on artifactr, evalr, reflexr and lattice-core; their changes rerun its tests. `test-pg` sets `RELAYR_TEST_POSTGRES_URL`; after a cached `test`, use `moon run relayr:test --force`.

## Generated files

`tests/test_openapi.py` fails when `schemas/relayr.openapi.json` differs from the routers. After changing a route, run `moon run relayr:schema`, then `moon run client:types` for portalr's client.

## Layering

`tests/test_layering.py` enforces it:

- `ledger` knows neither library; `sql` builds on `ledger` and `lattice_core.sql` only.
- Every name relayr imports from artifactr, reflexr or evalr must be in that module's `__all__`: public API only.
- Only `ui` imports `artifactr.ui`, and only `excalidraw` imports `artifactr.excalidraw`; `plane` and `vikunja` import `trackers` and httpx, nothing else of relayr.
- Neither library imports relayr; keep it that way.
- A new package under `src/relayr/` needs an entry in `LAYERS`.

## Conventions

- The `ledger` fixture in `tests/conftest.py` runs each test on memory, SQLite and PostgreSQL (plus a row-level-security role); write storage tests against it.
- Time comes from `tests/clock.py`'s `FakeClock`, never the wall clock.
- A run's effects happen once: derive ids and key edits so a retry is a no-op ([ADR-0019](../../docs/relayr/adr/0019-runs-act-once-through-derived-ids-and-keyed-edits.md)).
- A schema change is a new Alembic migration in `src/relayr/sql/`.

## Key ADRs

- [ADR-0002](../../docs/relayr/adr/0002-the-outbound-actor-an-external-agent-per-rule.md): the outbound actor is an external agent per rule.
- [ADR-0003](../../docs/relayr/adr/0003-a-thread-is-never-a-chain.md): a thread is never a chain.
- [ADR-0007](../../docs/relayr/adr/0007-notices-by-default.md): notices by default.
- [ADR-0015](../../docs/relayr/adr/0015-cursors-leases-and-dead-letters-in-the-ledger.md): cursors, leases and dead letters.
- [ADR-0018](../../docs/relayr/adr/0018-bridged-events-their-fields-ids-and-projections.md): bridged events.
- [ADR-0027](../../docs/relayr/adr/0027-row-level-security-under-the-scoping.md): row-level security.
- [ADR-0033](../../docs/relayr/adr/0033-the-tracker-port-and-runs-that-write-to-it-once.md): the tracker port.

## Pitfalls

- relayr never resolves a proposal; people do.
- Row-level security is only exercised on PostgreSQL; run `test-pg` for changes to `sql/` or `ledger/`.
- The tracker tests replay recordings; see [tests/trackers/AGENTS.md](tests/trackers/AGENTS.md).
