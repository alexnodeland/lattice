# ADR-0001: The hook hears the action

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Records decision D1 of [lattice RFC-0001][rfc], identity and access.

## Context

artifactr's and reflexr's `Authorize` hook is asked when a workspace is opened, with the tenant, the workspace and the actor, and never hears what the actor is about to do. A role such as "viewer" can't be kept from editing, so the libraries' guides tell applications to check commands in their own routes. Every surface then has to remember, in-process calls and agent tools included. The hook is also where the template's mirrors start a workspace's background work, so a permission check has side effects.

## Decision

- **`Authorize` takes an `Access`:** the action, as a qualified string such as `artifactr:edit_artifact`, and the thread, artifact or rule it is about. Its workspace is `None` for tenant-wide reads.
- **Each `Workspace` method asks it,** so every command and every read on every surface is checked, in one place. The hooks move onto `Workspaces`, and the surfaces stop taking their own.
- **Each library exports its catalog,** `ACTIONS`, the complete list, and grantr validates roles against the catalogs the application hands it.
- **Side effects move to `on_open`,** called after every allowed open, so a check has none.
- **grantr answers it** through `Grants.hooks(subject_of)`, which reads an `Access`'s fields by name and imports neither library.

## Options considered

| Option | For | Against |
|---|---|---|
| **Widen `Authorize` with an `Access`, asked per command and read; side effects on `on_open` (chosen)** | One hook, asked in one place, so no surface can forget it | Breaks every application's `authorize` |
| A second `permit` hook beside an unchanged `authorize` | No break | Three hooks in reflexr, and a surface can forget one |
| Checks in the routes | The libraries' advice today | Every surface remembers on its own, and they drift |

## Consequences

- Easier: a viewer can be kept from editing, on every surface at once, and the libraries' permission-matrix tests prove each surface asks.
- Harder: a breaking change in artifactr and reflexr, and a check per command and read.

[rfc]: ../../rfcs/0001-grantr-identity-and-access.md#decisions
