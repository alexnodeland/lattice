# ADR-0024: The reference implementation as a workspace member

**Status:** Accepted, amended by [ADR-0052](0052-artifactr-in-lattice.md)
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

[ADR-0013](0013-library-with-reference-implementation.md) calls for `examples/docplan`: a reference implementation built only on the public API, which doubles as the end-to-end test. Building it (RFC-0001 phase 6) required several decisions:

- how it is packaged and installed next to the library
- how "only the public API" is kept true
- how it is tested without calling a model API
- what it does about authentication, which is the host's concern

## Decision

- **A uv workspace member.** `examples/docplan` is its own distribution (`docplan`), a member of the repository's uv workspace. It depends on `artifactr[fastapi,mcp]` from the workspace, so it always runs against the library in the same commit. `uv sync --all-packages` installs it, and it provides two commands: `docplan-serve` and `docplan`.
- **Public API only, enforced.** A layering test fails if any docplan module imports an artifactr module other than a package's public surface (`artifactr`, `artifactr.core`, `artifactr.agent`, and so on).
- **The same quality gate as the library.** docplan is linted, type-checked strictly and counted in the 100% branch-coverage gate. Its tests run the real server (uvicorn on a free port) and the real terminal client over a real WebSocket. The agent's model is a scripted `FunctionModel`, so no test needs an API key.
- **Demo authentication, named as such.** The server trusts an `x-user` header and puts everyone in one tenant, and its docs say so. The code shows exactly where a real application plugs in its own `resolve_actor` and `resolve_client`.
- **The terminal client is a thin protocol client.** It builds command frames and renders event and live frames as plain JSON. It does not use artifactr's frame models, so it reads as a template for a client in any language.

## Options considered

### Where the reference implementation lives

| Option | Runs against the current library | Installed with one command | Kept honest about the API |
|---|---|---|---|
| **Workspace member (chosen)** | Yes | Yes | Yes, with the layering test |
| A module inside `artifactr` | Yes | Yes | No: it could reach private modules unnoticed |
| A separate repository | No: pins a released version | No | Yes |

### How it is tested

| Option | Covers the wire | Deterministic |
|---|---|---|
| **Real server and client, scripted model (chosen)** | Yes: HTTP, WebSocket and MCP over a socket | Yes |
| In-process `TestClient` only | Partly: not the WebSocket client | Yes |
| A live model | Yes | No, and it needs a key |

## Consequences

- Easier: a new contributor can run a complete application with two commands, and read one small codebase that uses every extension point.
- Easier: API gaps surface as failing example tests. Building docplan found four, each fixed in the library in its own pull request:
  - artifact reads did not carry the artifact's `kind`
  - a tool's own `ModelRetry` left no `tool_returned` event
  - the stream sent live frames from threads a client did not follow, and kept watchers for long-ended runs
  - proposed edits had no summary for reviewers
- Harder: the library's CI now installs docplan's dependencies (uvicorn, websockets, rich, prompt-toolkit, and the Anthropic and OpenAI SDKs).
- Revisit: switch docplan to SQL storage by configuration once `artifactr.sql` lands.

## Action items

1. [x] Create `examples/docplan` as a workspace member with its server, client, README and tests.
2. [x] Enforce public-API-only imports in the layering test.
3. [x] Let docplan use `artifactr.sql` storage by configuration (`DOCPLAN_DATABASE_URL`).
