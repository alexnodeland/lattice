# ADR-0096: Every request portalr's client sends names its command

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** lattice [RFC-0014](../../rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md)'s P13, the client's side of parity (#916), on lattice [ADR-0042](../../adr/0042-parity-every-operation-names-its-command-and-one-test-holds-the-catalogs-to-grantr.md)

## Context

RFC-0014 holds every action a person takes in portalr to a command of the libraries' catalogs, so that what a person can do in portalr, an outside client can do through portr. lattice ADR-0042 put the libraries' side in place: every operation of their OpenAPI documents says what it calls in `x-lattice-command`, and `tests/test_parity.py` holds the documents, the catalogs and grantr's actions to each other.

The client's side was missing. `@portalr/client` sent requests through openapi-fetch's clients, typed from each document. Nothing tied a request to the command its operation calls, or listed which commands portalr's UIs send. A command could be dropped from a catalog, or an operation's command changed, and the client would compile and send as before.

## Decision

- **`client:types` writes `Calls`** (`src/generated/calls.ts`) from each document's `x-lattice-command`, by surface, path and method. Each operation is typed as one of:
  - its command;
  - the commands a caller picks one of, as grantr's `POST .../grants` is `grantr.grant` or `grantr.grant_on_tenant`;
  - `null`, for one that calls none, such as `config.json` or the analytics relay;
  - `"frames"`, where the body carries command frames, each named by its `type`.
- **Every request names its command first.** `Api`'s clients are openapi-fetch's, wrapped by `withCommands`: each method takes the operation's command before its path, as in `api.grantr.DELETE("grantr.revoke_key", "/grantr/v1/tenants/{tenant}/keys/{key_id}", init)`. `tsc` fails on a request that names another command, or none where the operation calls one. The name isn't sent: the server knows what each operation calls.
- **A request names its command with a literal,** or a conditional of literals where the caller picks one. `commands.used.json`, beside the client's `src`, lists every command the UIs' requests name: `client`, `app`, `admin` and `ui`, tests and generated files apart. `client:types` writes it from their sources. Its drift test regenerates it and compares, and fails on a request that names its command any other way, so the list can't miss one.
- **The parity test reads `commands.used.json`:** it fails on a command the client sends that no catalog declares, or that isn't offered on `portalr`.
- The streams' commands are named by their frames' `type`, which the protocols' schemas type; `commands.used.json` lists the REST requests' alone.

## Options considered

### Option A: Name the command at each request, typed from `x-lattice-command` (chosen)

**Pros:** each request says what it calls where it is written, and `tsc` holds it to the document. A changed command fails the build at every request that sends it.
**Cons:** every request changes: 86 of them, mostly in `queries.ts` and `commands.ts`.

### Option B: A middleware that checks each request against a map at run time

**Pros:** no request changes.
**Cons:** a gap shows only when the request is sent, in a test that happens to send it, and nothing lists what the UIs send.

### Option C: Tag the UIs' components with the command each action calls

**Pros:** the closest to "every action a person takes".
**Cons:** components don't send requests; the client does. A tag on a component is a claim no type checks, and RFC-0014 left tagging out.

## Consequences

- Easier: a command dropped or renamed in a catalog, or an operation that calls another, fails `client:typecheck` at each request that sends it, once `client:types` has run.
- Easier: what portalr sends is a file, which the parity test and, later, portr's coverage can read.
- Harder: a request names its command, as a literal, before its path.
- To revisit: the streams' commands in `commands.used.json`, read from the frames the stores send.
