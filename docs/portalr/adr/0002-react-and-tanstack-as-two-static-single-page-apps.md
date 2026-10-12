# ADR-0002: React and TanStack, as two static single-page apps

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Records decision P2 of [lattice RFC-0002][rfc-0002], portalr, the portal.

## Context

portalr has two UIs: `app`, for the people who use an application, and `admin`, for those who run it. Both are behind a sign-in, with no pages to index, and the data lives in the Python application. The family has been Python only, so this is its first frontend stack, and it is chosen once for both UIs.

## Decision

- **React 19 and TanStack:** TanStack Router with file-based routes, Query for caching and invalidation, and Table and Virtual for long lists.
- **Two static single-page apps, built by Vite,** which portalr's router serves. The same build serves every deployment, reading what differs from a small `config.json`.
- **No server rendering and no Node server.**

## Options considered

| Option | For | Against |
|---|---|---|
| **React 19 and TanStack, as two static apps on Vite (chosen)** | The components the admin UI vendors are React's: AgentPrism, Tremor and Base UI. Static files served by the Python application, with nothing else to deploy | Two builds to keep consistent, which the shared `ui` kit only partly solves |
| TanStack Start, with server rendering and a Node server | One framework from routes to data | A process to deploy for nothing these UIs need: no page is public, and the data is in the Python application |
| Svelte 5 | Less code per component | The trace view, charts and primitives the admin UI vendors ([ADR-0004](0004-native-views-of-a-tenants-observability.md)) would have to be rewritten, not ported |

## Consequences

- Easier: portalr's wheel carries the built UIs, and an application serves them from its own origin, so there is no CORS or CSRF to configure.
- Harder: a second language in the family, with its own toolchain, lockfile, linters and tests.

[rfc-0002]: ../../rfcs/0002-portalr-the-portal.md#decisions
