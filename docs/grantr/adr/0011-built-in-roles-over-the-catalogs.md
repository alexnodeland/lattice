# ADR-0011: Built-in roles over the catalogs

**Status:** Accepted, amended by [ADR-0019](0019-runtime-actions-and-the-application-role.md) [ADR-0022](0022-a-tenants-members-list-its-workspaces.md) and [ADR-0023](0023-portalrs-admin-reads.md)
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

Lattice RFC-0001's role table says what each built-in role may do in words, and that workspace roles are defined by action names in the libraries' catalogs, which the application hands grantr. The libraries' catalogs come with phase 1, which hasn't landed, and the table doesn't say where a grant on a rule may go.

## Decision

- **A built-in role is resolved against the catalogs when `Grants` is made,** by the level it is granted at: the deployment, a tenant, a workspace, or an item (a thread, artifact or rule). `admin` is two roles, one on a tenant and one on a workspace.
- **`viewer` holds every `read_` action and every `open`,** by name, and the libraries' `give_feedback`, so a library's new read lands in it.
- **`editor` adds the commands it names,** as phase 1 is expected to name them after the libraries' commands: posting, creating threads and artifacts, editing, proposing, archiving, resolving proposals, answering deferred calls, focus and thread mode, publishing events, and retrying, skipping and cancelling runs. A name the catalogs don't have grants nothing, and a new command lands in no built-in role until it is added here, in a reviewed change.
- **A workspace `admin` holds every library action,** rule management included, and `grantr:grant`, `revoke` and `restrict`. A tenant `owner` holds every action in every catalog but the operator's, and a tenant `admin` the owner's but `grantr:delete_tenant`. `member` holds nothing.
- **`editor`, `viewer` and custom roles may be granted on a rule** as on a thread or artifact, since a grant may name a rule and reflexr's rule commands name one.
- **A custom role** holds only actions a workspace's admin holds, since it is granted in a workspace, and can't take a built-in name. A grant whose role can't be at its resource holds nothing.

## Options considered

| Option | For | Against |
|---|---|---|
| **Roles resolved against the handed-in catalogs, with `read_` by prefix and commands by name (chosen)** | What the RFC describes; an application with only reflexr gets only reflexr's actions | `editor`'s names are fixed before phase 1 names the catalogs |
| Each library declares its own role membership | No names in grantr | grantr's roles would be defined in two libraries, and the libraries would know grantr's roles |
| Workspace roles not grantable on rules | The RFC table read literally | A grant on a rule could name no role but a custom one |

## Consequences

- Easier: a library's new read is visible to viewers at once, and portalr's tenant-level reads reach tenant owners and admins without a change here.
- Harder: if phase 1 names a command differently, `EDITOR_COMMANDS` changes with it; the matrix snapshot of phase 4 makes that a reviewed change.
