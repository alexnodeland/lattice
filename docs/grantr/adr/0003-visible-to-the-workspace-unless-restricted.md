# ADR-0003: Visible to the workspace unless restricted

**Status:** Accepted, amended by [ADR-0024](0024-who-sees-a-restricted-item.md)
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Records decision D3 of [lattice RFC-0001][rfc], identity and access.

## Context

With grants on threads and artifacts ([ADR-0002](0002-grants-down-to-threads-and-artifacts.md)), a new item needs a default visibility. Whatever is the exception is what `hidden` returns, and what each listing filters out.

## Decision

- **A new thread or artifact is visible to everyone with a role in its workspace.**
- **A restricted one** is visible only to those granted a role on it, the workspace's admins, and the tenant's owners and admins. The flag is set and cleared with `grantr:restrict`.
- **`hidden` returns the exceptions,** so its sets are small, and a library filters with `id NOT IN (...)` in SQL or a set lookup in memory.

## Options considered

| Option | For | Against |
|---|---|---|
| **The workspace's, unless restricted (chosen)** | Collaboration is the default, as today. The hidden sets stay small | Restricting is a step someone has to remember |
| Private to its creator until shared | Safe by default | Every item has to be shared before anyone else sees it, and the hidden sets grow with the workspace |

## Consequences

- Easier: workspaces behave as they do today until someone restricts an item.
- Harder: an open live stream learns of a new restriction only when it fetches the sets again, up to `hidden_refresh` later.

[rfc]: ../../rfcs/0001-grantr-identity-and-access.md#decisions
