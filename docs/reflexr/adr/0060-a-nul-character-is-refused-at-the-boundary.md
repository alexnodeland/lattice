# ADR-0060: A NUL character is refused at the boundary

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

PostgreSQL's `text` can't hold a NUL character. reflexr stores ids, names and types in text columns, so a string with one answered 500 on PostgreSQL, while SQLite and the in-memory storage took it ([lattice #67](https://github.com/alexnodeland/lattice/issues/67)). Schemathesis found it with `GET /v1/workspaces/w/runs?scope_key=%00`, and the Acceptance job ran with `allow-x00 = false` until it was fixed.

Bodies are stored as JSON, not JSONB, and PostgreSQL's `json` does take an escaped NUL. So only some strings failed: those that reach a text column, such as ids, names, a run's scope key and a cursor's name.

## Decision

- **Every `Workspaces` and `Workspace` method refuses a NUL character** in any string it is given, with `validation_failed` (`text cannot hold a NUL character`). This covers ids, names and actors, and every string an event, feedback, a rule or its provenance carries, nested in models, mappings and collections.
- **A command id with a NUL** is answered with a `validation_failed` command result by `Workspaces.execute`, as every rejection is there, and remembered under no key, since storage couldn't hold it.
- **The rule is uniform.** It covers strings that would land in a JSON body as well as those in a text column, so what a client may send doesn't depend on where the library keeps it.
- **It is checked before `authorize`.** The hook is a boundary too: grantr's SQL adapter would meet the same NUL in a tenant or workspace id. Counts and `seq` numbers are checked after the hook, since a number can't hurt it.
- **One helper, `_check_text`,** shared verbatim with artifactr's workspace module, is called at the top of each method.

## Options considered

| Option | Covers | Against |
|---|---|---|
| **At the workspace boundary (chosen)** | Every surface and every storage, in-process calls included | A call in each method |
| In each route and tool | REST and MCP | In-process calls and the WebSocket left out, and a check per route |
| Constrained id types in core | Models and FastAPI's parameters | Not function arguments, and FastAPI's 422 isn't a `validation_failed` rejection |
| In the SQL adapter | PostgreSQL only | The storages answer differently, and the hook still hears the NUL |

## Consequences

- Easier: every storage answers a NUL alike, and a NUL is a client's mistake, not a server error.
- Harder: a string with a NUL that SQLite or the in-memory storage took before is now refused.

## Action items

1. [x] `_check_text` in every `Workspaces` and `Workspace` method, with a table of calls run against every storage.
2. [x] The root `schemathesis.toml` keeps `allow-x00 = false`, with this reason: the document can't say of every string that it refuses a NUL, so a NUL would fail `positive_data_acceptance`.
