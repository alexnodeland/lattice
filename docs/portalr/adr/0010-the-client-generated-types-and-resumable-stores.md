# ADR-0010: The client: generated types, and resumable stores

**Status:** Accepted, amended by [artifactr ADR-0063](../../artifactr/adr/0063-the-openapi-documents-describe-refusals.md), [reflexr ADR-0061](../../reflexr/adr/0061-the-openapi-documents-describe-refusals.md) and [reflexr ADR-0064](../../reflexr/adr/0064-the-protocol-schema-names-reflexrs-own-events.md)
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[lattice RFC-0002](../../rfcs/0002-portalr-the-portal.md#client) makes `@portalr/client` the only code in the UIs that talks to the server. Its types are generated from each package's committed documents, never written. Its REST calls go through `openapi-fetch` and TanStack Query. It keeps a WebSocket store per stream that resumes by `seq`, and one reducer per protocol whose exhaustiveness the compiler checks. [ADR-0007](0007-typescript-7-and-6-only-where-a-tool-needs-its-api.md) left phase 3 to settle where `openapi-typescript`, which needs TypeScript 6, runs.

The documents are artifactr's and reflexr's OpenAPI documents and WebSocket JSON Schemas, reflexr's rules schema, and grantr's OpenAPI document. Two of their traits shape the code:

- **pydantic marks a discriminator with a default as optional,** so `type` is optional on every frame and event, and a union can't be narrowed on it.
- **reflexr's events are open:** its schema types an event as `{type, ...}`, since the application's events share the log with reflexr's own. artifactr's schema names every event, and keeps one it doesn't know as `UnknownEvent`.

## Decision

- **`scripts/generate.ts` writes `src/generated/`:** `openapi-typescript` 7.13.0 for the three OpenAPI documents, and `json-schema-to-typescript` for the three JSON Schemas. A drift test calls the same function and fails if a committed file differs; `moon run client:types` rewrites them.
- **A constant property is required,** since every frame and event carries its discriminator, so the unions narrow on `type`. At first the generator made it so before compiling the schemas; the schemas now say so themselves ([#82](https://github.com/alexnodeland/lattice/issues/82)), and the transform is gone.
- **TypeScript 6 is `client`'s own `typescript`,** as `npm:typescript@6.0.3`, which `openapi-typescript` loads. Bun's isolated installs keep it to `client`, and `client`'s `typecheck` runs the root's TypeScript 7 by its path, so every package is still checked with 7.
- **`json-schema-to-typescript` is at 15.0.4.** 16.0.0 needs js-yaml 5, and the root's `overrides` hold js-yaml at 4.3.2 for the Bruno CLI. Renovate holds it below 16, and `client`'s TypeScript at 6.
- **REST:** `createApi(surfaces, session)` makes one `openapi-fetch` client per surface, each request carrying the session's `Authorization` and `X-Tenant`. `createQueries(api)` makes TanStack Query's options for every read. `keys` nests each read's key under its workspace, then splits each resource into its `list` and each `detail`, so invalidating the workspace refetches everything read from it, and a list refetches without its details. `stale.artifactr` and `stale.reflexr` name the reads an event makes stale; `stale.artifactr` lists every event artifactr's schema names. `@tanstack/react-query` is a peer dependency; app and admin own the `QueryClient`.
- **A `Stream` per workspace stream,** generic over the protocol, which classifies each frame for it (welcome, replay complete, event, result, error, or another, such as a live frame):
  - It says `hello` from the last `seq` it applied, applies each event once and in order, skips an event at or below that `seq` (a frame sent twice, or a replay overlapping a tail read over REST), and follows `replay_complete` to `live`. With `fromHead`, its first `hello` starts at the head, and it resumes from `welcome`'s `head_seq` after.
  - On a drop it reconnects after a random wait up to a ceiling that grows from 100 ms to 5 seconds, and resumes. On `welcome` with `reset` it discards its state and rebuilds from the replay. After 4400, 4401 or 4403 it stops. Its URL is a function, read at every connect, so `reconnect()` after a refreshed token, or after 4401, connects with the new one.
  - A command carries a `command_id`, and a command still unanswered when the connection drops is sent again with the same id. It settles as `done`, `refused` or, if the store is closed first, `closed`. A create the client chose an id for, sent again and refused as `invalid_state`, is `done`, since the first try made it; for `post_message`, `done` means the message was posted, not that its turn ran.
  - An `error` frame's message is in the snapshot.
  - A browser's WebSocket can't send headers, so `streamUrl` puts the session in the query, as `access_token` and `tenant`.
  - Components read it through `subscribe` and `snapshot`, which `useSyncExternalStore` takes.
- **artifactr's reducer has a handler for every event its schema names,** typed as a mapped type over them, so the compiler fails when the schema gains one. An unknown event changes nothing.
  - Its state holds threads with their messages, artifacts' kinds and latest versions, proposals' statuses, and runs, with their tools and the text they are streaming. An artifact's content is read over REST.
- **reflexr's reducer handles reflexr's own run and rule events by name,** and reads their fields as JSON, without redeclaring their types, until reflexr's schema names them ([#83](https://github.com/alexnodeland/lattice/issues/83)). Its state holds stored rules, with their firings, and runs, with their statuses.
- **The tests:**
  - Unit tests run against a scripted stream server on `Bun.serve`: a drop mid-stream, a frame sent twice, a tail, a start at the head, a reset, a reset whose replay is cut short, a command resent after a drop, a create refused on its retry, closing with commands unanswered, an error frame, a refusal that stops the store, a reconnect with a refreshed token, and a reconnect during the backoff.
  - `client:api` starts docplan and oncall from their libraries' compose files, and runs Vitest's `api` project against them in CI's Acceptance job. A client there closes, events are committed over REST while it is away, and it opens again: it applies every `seq` from 1 to the head once.

## Options considered

| Option | For | Against |
|---|---|---|
| **Types generated by two tools, and a store per stream over one generic `Stream` (chosen)** | Every type is the server's own. One resume, one command path, for both protocols | Two generators, and a TypeScript 6 alias beside one of them |
| Hand-written types for the WebSocket frames | No generator for JSON Schema | Copies of the server's types, which drift from them unless something checks; lattice RFC-0002 rules them out |
| A codegen package of its own, holding `openapi-typescript` and TypeScript 6 | `client`'s `tsc` would be 7 without a path | A fifth web package, for one script |
| Typing reflexr's own events by hand | A typed reflexr reducer | Copies reflexr's models; the fix belongs in reflexr's schema |

## Consequences

- Easier: a change to any package's document fails `client`'s drift test, and a new artifactr event fails its typecheck until the reducer and `stale.artifactr` handle or ignore it.
- Easier: app and admin read state through one store per stream and one set of query keys.
- Harder: reflexr's reducer and `stale.reflexr` read its events by name, and nothing checks them against reflexr's events until its schema names them ([#83](https://github.com/alexnodeland/lattice/issues/83)).
- To revisit: the TypeScript 6 alias goes when `openapi-typescript` supports TypeScript 7's API.
