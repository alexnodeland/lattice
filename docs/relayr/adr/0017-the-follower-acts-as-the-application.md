# ADR-0017: The follower acts as the application

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

A follower opens each workspace in both libraries, and since lattice [RFC-0001](../../rfcs/0001-grantr-identity-and-access.md) every `Workspace` method asks `authorize` with the action it takes. With grantr wired, the template's `subject_of` maps each actor to a grantr subject, and checks are deny by default. RFC-0002 names the actor on every bridged envelope, `SourceActor("artifactr")`, and warns that no client may ever resolve to it, since rules trust it until reflexr can reserve a type to one source ([lattice #8][l-8]). It doesn't say whom the follower reads artifactr as, or what either actor may do.

## Decision

- **In artifactr, the follower is `SystemActor(name="relayr")`** (`relayr.inbound.FOLLOWER`). It only reads: `artifactr:open` and `artifactr:read_events`. Its cursor is in the ledger, so it needs no `artifactr:save_cursor` or `read_cursors`.
- **In reflexr, it is `SourceActor(name="artifactr")`** (`relayr.inbound.SOURCE`), the actor RFC-0002 gives every bridged envelope. It takes `reflexr:open` and `reflexr:publish`.
- **In grantr, both are the application's own service principal.** The template's `subject_of` maps a `SystemActor` there already, by lattice RFC-0001's table, and maps the source `artifactr` there too, rather than to a principal of that source's own. The `application` role planned in grantr's [ADR-0019][g-adr-0019] holds all four actions in every tenant: every `open` and read, and `reflexr:publish`.
- **No client resolves to `SourceActor("artifactr")`.** The template's resolvers make users, external agents and service principals' clients, never that source.

## Options considered

| Option | For | Against |
|---|---|---|
| **The application's principal (chosen)** | relayr is the application's own code, in its process; one grant, made when the application starts, covers every tenant | The application's role must hold what relayr does |
| A service principal of relayr's own | Its grants apart from the application's | A grant in every tenant, made as each is created, or the bridge stops in new tenants |
| A user, such as the workspace's admin | Nothing new in grantr | Acts with a person's authority, and misattributes every bridged event |

## Consequences

- Easier: a new tenant's workspaces are bridged as soon as they are opened, with no grant to remember.
- Harder: until grantr's `application` role lands, and the template wires `subject_of` (grantr's phase 4), an application that closes access with grantr must grant those four actions itself.
- The test that pins the four actions is `tests/inbound/test_followers.py`.

[g-adr-0019]: https://github.com/alexnodeland/lattice/pull/65
[l-8]: https://github.com/alexnodeland/lattice/issues/8
