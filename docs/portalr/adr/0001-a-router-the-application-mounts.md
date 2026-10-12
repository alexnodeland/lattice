# ADR-0001: A router the application mounts

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Records decision P1 of [lattice RFC-0002][rfc-0002], portalr, the portal.

## Context

portalr's UIs need the libraries' data: artifactr's threads and artifacts, reflexr's rules and runs, grantr's access. Something on the server has to serve the UIs, and the few reads no library has, such as a tenant's traces and spend. The work codebase put a backend of its own in front of its chat service, and paid for it: types copied by hand in three places that drifted, a user passed on in a plain header the chat service trusted, and per-workspace fan-outs that exhausted the chat service's database pool. stackr RFC-0003 called portalr's Python side "the console service" and left its design to the portal RFC.

## Decision

- **portalr's Python side is a router,** `portalr_router`, which the application mounts beside the libraries' routers, as it mounts theirs.
- **It serves the two built UIs** at `/portalr/app/` and `/portalr/admin/`, and adds only what no package has, under `/portalr/v1`: reading the stack's shared tools for one tenant, and inviting users.
- **The browser calls each package's own routes,** on one origin, with one token. A chat goes to artifactr's WebSocket, a rule to reflexr's REST, a grant to grantr's API. Nothing proxies them.
- **This amends stackr RFC-0003,** whose "console service" is this router.

## Options considered

| Option | For | Against |
|---|---|---|
| **A router the application mounts (chosen)** | Each package's types reach the browser from its own document, generated. The user each package sees is the one the token names. No process to deploy | The UIs depend on every package's API directly |
| A separate backend in front, proxying every package | One API for the UIs to call | Every library type copied or proxied, and the user passed on as a header: the work codebase's shape, and its bugs |

## Consequences

- Easier: a package's API change reaches the UIs through its committed document and `client`'s drift test, not through a copy someone has to remember.
- Easier: an application deploys nothing extra; portalr is a wheel and a mount.
- Harder: a breaking change in a package's protocol breaks the UIs until `client` is regenerated, which the drift test makes loud but not free.

[rfc-0002]: ../../rfcs/0002-portalr-the-portal.md#decisions
