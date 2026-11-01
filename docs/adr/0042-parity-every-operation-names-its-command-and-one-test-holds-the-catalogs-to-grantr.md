# ADR-0042: Parity: every operation names its command, and one test holds the catalogs to grantr

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** [RFC-0014](../rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md)'s parity test (P13, #916), on [ADR-0041](0041-the-command-declaration-a-capability-with-its-toolset-exposure-route-and-surfaces-in-a-static-catalog.md)'s catalogs

## Context

RFC-0014 asks for parity between portalr, MCP and grantr in features not yet written: every action a person takes is a command, every command reaches outside clients or says why not, and every command is checked by grantr. A checklist is missed; a test over declarations is not. P13 picks the mechanism: an `x-lattice-command` extension on every operation of each library's OpenAPI document, command frames' `type`, the client's `CommandName` and manifest, and a root `tests/test_parity.py`.

Every package's catalog is now declared: artifactr's, grantr's, reflexr's, relayr's and portalr's. evalr has none, since it has no service of its own. The libraries publish seven OpenAPI documents, of 106 operations, and grantr composes every library's actions in `Catalog.of(...)`.

## Decision

- **Every operation says what it calls,** in `x-lattice-command`, written by one of `lattice_core.commands`' helpers through FastAPI's `openapi_extra`:
  - **`calls(name, ...)`:** the command it calls, such as `grantr.list_members`. An operation that calls one of several by its arguments names each: grantr's `POST .../grants` is `grantr.grant` or `grantr.grant_on_tenant`.
  - **`carries_frames(member, **none)`:** the member of its body that holds a command frame, as artifactr's and reflexr's `POST .../commands` do. Each frame's `type` names the action it asks, `<package>:<type>`, as on the stream, and that action must be some command's gate. A frame that asks no action says why: artifactr's `watch_run`, `watch_artifact` and `unwatch_artifact` are the stream's subscriptions, refused on REST.
  - **`calls_none(reason)`:** why it calls none. Either it is no action (`config.json`, `/me`, `/checks`, a person's own analytics consent, a tracker's webhook), or its command comes later, with its issue (native files' upload and check-out, #924).
- **An operation names the command a person means by it,** whichever package declares it. Several operations may name one command: artifactr's file text, pages and download all read `artifactr.read_file`. grantr's own `GET` and `POST /tenants` name portalr's `portalr.list_deployment_tenants` and `portalr.create_tenant`, since RFC-0014 makes creating a tenant portalr's command.
- **`called(extension)`** reads it back for the test, and refuses anything the helpers don't write.
- **`tests/test_parity.py`** composes the five catalogs, grantr's `Catalog.of` over artifactr's, reflexr's and portalr's actions, the actions each library lists with a reason, and every `packages/*/schemas/*.openapi.json`. It fails on each gap in the table below, and each gap has a fixture that fails it: a catalog without a command, an operation without its extension, a gate grantr lacks, and so on.
- **The test found one gap on its first run:** grantr's `GET .../restrictions` read a list no command offered. grantr's catalog gains `grantr.list_restrictions`, gated by `grantr:restrict`.
- **Still to come, in #916:** portalr's client naming the command of everything it sends, with `CommandName` generated from the catalogs and `commands.used.json`. portr's generated tools follow in #917, and the test will hold them to each command's exposure.

| Gap | Check |
|---|---|
| An operation calls no command | each has a readable `x-lattice-command`, whose commands are in the catalogs, and whose frames' types are gates or say why not |
| A command has no tool | its exposure is `tool`, `resource` or `both`, or `NotExposed` with a reason |
| A command is in no toolset | its toolset is one of `TOOLSETS` |
| A tool has no grantr check | its gate is in grantr's catalog |
| A grantr action has no command | it is some command's gate, or listed by its library with a reason; and nothing listed is a gate, or no action |

## Options considered

### Option A: The extension on every operation, and the test in root `tests/` (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one keyword argument per route, one test module |
| Where a gap shows | in the document, beside the route, and in the test's message |

**Pros:** each route says what it calls where it is written, and the generated document carries it, so the client's generator and the test read the same thing. A reason not to name a command is written at the route.
**Cons:** 106 routes changed at once, and every new route needs the argument, which the test enforces.

### Option B: An allowlist in the test

**Cons:** the reason a route calls no command lives far from the route, and the document doesn't say what a route calls, which the client's `CommandName` needs.

### Option C: Matching operations to commands by path or name

**Cons:** paths and names differ between REST and tools (`GET .../rules/{rule}` is `reflexr.get_rule`, `POST .../grants` two commands), so any rule would need exceptions as long as the routes.

## Trade-off analysis

Option A costs a line per route and wins where the gaps show: the route, the document and the test agree. Matching by rule (C) would spend that line on exceptions, and an allowlist (B) puts the reasons out of sight of the routes they excuse.

## Consequences

- Easier: a new route, command or action that misses its counterpart fails `lattice:test`, with a message that names the gap.
- Harder: every route a library adds takes `openapi_extra`, and every action a command or a reason.
- The libraries' documents change by an extension only, which `client:types` doesn't carry into the client's types.
- To revisit: the client's side and portr's tools (#916, #917); the catalogs composed through RFC-0011's entry points once the libraries register them, where the test imports each catalog today.
