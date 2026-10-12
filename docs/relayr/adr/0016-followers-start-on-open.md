# ADR-0016: Followers start on open

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Amends [stackr RFC-0002][rfc-0002-inbound]: its followers start through the libraries' `on_open` hook, not their `authorize` hook.

## Context

RFC-0002 starts a workspace's follower "the first time a workspace is used, through the libraries' `authorize` hook, as the template's `Mirrors` does for feedback", and its template section wires "followers started through the `authorize` hook". Lattice [RFC-0001](../../rfcs/0001-grantr-identity-and-access.md#the-widened-hook) has since moved the hooks onto `Workspaces(authorize=, on_open=)` in both libraries. `authorize` is asked for every command and read, so it must have no side effects; `on_open` is called on every allowed open, after the check, and its callees are idempotent. The template's mirrors moved to `on_open` in that RFC's phase 1.

## Decision

- **`Followers.watch(tenant_id, workspace_id)` is an `OnOpen`.** It starts the workspace's follower unless it runs already, so it does nothing on every open after the first, the follower's own included.
- **The application gives it to both libraries' `Workspaces`.** Each takes one `on_open`, so the template composes `watch` with the mirrors' into one function. Opening a workspace in either library then starts its follower.
- **At startup, `Followers.resume()` follows every workspace the ledger knows** ([ADR-0015](0015-cursors-leases-and-dead-letters-in-the-ledger.md)). A workspace used for the first time since the bridge was installed is followed once someone opens it, until artifactr can list a tenant's workspaces ([lattice #5][l-5]).
- **A follower that stopped starts again the next time its workspace is opened,** as a mirror does.

## Options considered

| Option | For | Against |
|---|---|---|
| **`on_open` (chosen)** | Called after the check, on every allowed open; the hook lattice RFC-0001 made for this | One more callback to compose in the template |
| `authorize`, as RFC-0002 wrote | No composition | It is asked for every command and read, and a check must have no side effects |
| Started by the application, for workspaces it lists | No hook | Nothing lists workspaces yet (lattice #5) |

## Consequences

- Easier: a permission check stays a check, and a follower starts exactly where a mirror does.
- Harder: the template's `on_open` has two callees, each of which must stay idempotent.

[l-5]: https://github.com/alexnodeland/lattice/issues/5
[rfc-0002-inbound]: ../../stackr/rfcs/0002-the-combined-system.md#inbound-artifactr-to-reflexr
