# AGENTS.md: lattice-core

Root [AGENTS.md](../../AGENTS.md) applies; this adds what is specific to lattice-core.

lattice-core holds the infrastructure two or more lattice packages share and must keep identical ([ADR-0018](../../docs/adr/0018-lattice-core-what-the-libraries-share.md)). It is distributed as **`lattice-core-ai`** and imported as `lattice_core`. Its pages are [docs/lattice-core/](../../docs/lattice-core/index.md).

## What belongs here

- Only code that is the same in two or more packages, never a package's domain. If one package uses it, it stays there.
- Applications never import from here: each package re-exports what it makes public. Keep names stable; every library depends on them.
- Settings are declared here and only narrowed below ([ADR-0030](../../docs/adr/0030-settings-typed-declared-in-lattice-core-and-only-narrowed-below.md)).

## Layout

| Path | What it is | Extra |
|---|---|---|
| `src/lattice_core/schema.py`, `text.py`, `origins.py`, `tags.py`, `refusals.py`, `logs.py`, `settings.py`, `integrations.py` | Shared helpers: tagged-union schemas, `holds_nul`, origins, the refusal schema, logging, settings, integration switches | none |
| `src/lattice_core/sql/` | The storages' shared SQL helpers: sessions, SQLite, tenancy | `sql` |
| `src/lattice_core/otel/` | OpenTelemetry setup; `otel/contribution.py`, the telemetry contract, needs no extra ([ADR-0020](../../docs/adr/0020-the-telemetry-contract-needs-no-extra.md)) | `otel` |
| `src/lattice_core/langfuse.py` | Langfuse's span filters | `langfuse` |
| `src/lattice_core/litellm.py` | The LiteLLM model | `litellm` |
| `typings/opentelemetry/` | Stubs for untyped OpenTelemetry modules | |

## Tasks

Only the inherited ones: `lint`, `typecheck`, `test`, `format`, `check`, plus `build`, `standalone` and `deptry`. No schema, PostgreSQL or API tasks. A focused run is `uv run pytest packages/lattice-core/tests/<path>.py -n0`. It has no `conftest.py`.

A change here affects every dependent: run `moon run :check`, not just `lattice-core:check`.

## Layering

`tests/test_layering.py` enforces, per module:

- Shipped code imports only the standard library and pydantic, and **never a lattice package**.
- An extra's module imports only what its extra installs (`EXTRAS`), and no other module imports it.
- Some imports are allowed only lazily, inside a function or under `TYPE_CHECKING` (`LAZY`); `fastapi` and `asyncpg` are never installed by an extra.
- `lattice_core` must import with no extra installed; a subprocess test checks it.

A new extra or module updates `EXTRAS`, `INSTALLS`, `LAZY` or `BASE` in the test and `[project.optional-dependencies]` together.

## Pitfalls

- The PyPI name `lattice-core` is someone else's; dependencies say `lattice-core-ai`.
- The `langfuse` extra reads Langfuse 4's propagated tags by an internal key ([ADR-0022](../../docs/adr/0022-litellm-requests-carry-the-propagated-trace-tags.md)); keep the `<5` cap.
- The refusal schema needs no extra ([ADR-0021](../../docs/adr/0021-the-refusal-schema-needs-no-extra.md)); don't make `refusals.py` import FastAPI.
- Wheels are checked at their dependency floors ([ADR-0029](../../docs/adr/0029-each-wheel-checked-at-its-floors.md)): don't use an API newer than the floor in `pyproject.toml`.
