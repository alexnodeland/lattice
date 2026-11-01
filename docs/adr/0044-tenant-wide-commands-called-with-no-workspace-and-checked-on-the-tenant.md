# ADR-0044: Tenant-wide commands, called with no workspace and checked on the tenant

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** [RFC-0014](../rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md)'s gateway (#917), before portr's MCP server; beside [ADR-0041](0041-the-command-declaration-a-capability-with-its-toolset-exposure-route-and-surfaces-in-a-static-catalog.md) and [ADR-0037](0037-the-enforcement-path-in-lattice-core-refusals-by-step-approvals-resumed-by-id.md)

## Context

Every call through the enforcer carries a `Scope`, and a scope named a tenant and one of its workspaces. Most commands act in a workspace: posting a message, editing an artifact, listing rules. Some act on the tenant as a whole:

- listing the workspaces a person can open (`artifactr.list_workspaces`);
- everything on access, such as granting a role or issuing a key (grantr's catalog);
- the tenant and member portalr makes.

Called through the enforcer, such a command still needed a workspace in its scope, though its handler reads only the tenant. An outside client of portr has none to give: it finds one with `artifactr.list_workspaces`, and that call would need a workspace to be made. A tenant-wide call given some workspace is also checked in the wrong place: a grant held on that one workspace would let someone list every workspace, and an integration or a setting narrowed there would decide a call about the whole tenant.

The owner chose on 2026-11-01:

- a client of portr names a workspace as an argument of each workspace-scoped tool;
- commands declare whether they are tenant-wide, and the enforcer resolves a tenant-wide call at the tenant.

## Decision

- **`Scope.workspace_id` is optional** (`lattice_core.capabilities`, contract 1.1.0). `None` is the tenant as a whole. `Owner.workspace_id` in `lattice_core.secrets` is already optional the same way.
- **`Command.tenant_wide`** (`lattice_core.commands`, contract 1.1.0) is false by default. A tenant-wide command is called with a scope that names no workspace, and a surface asks its caller for none. It is refused if its route or its resource names `{workspace}`.
- **Marked tenant-wide:**
  - `artifactr.list_workspaces`;
  - every grantr command;
  - every portalr command.

  reflexr's and relayr's commands, and the rest of artifactr's, act in a workspace.
- **The ports resolve a call with no workspace at the tenant:**
  - `Integrations.is_enabled(tenant, None, key)` is the tenant's state: the installation and the tenant's setting, with no workspace below them.
  - `Settings.value(tenant, None, key)` is the tenant's value: the operator's and the tenant's, which no workspace narrows.
  - grantr's `Authorize` checks the gate on the tenant, so only a role held on the tenant allows a tenant-wide call. A role held on one workspace doesn't.
  - An approval that a tenant-wide call asks for has the tenant's answerers: those who hold the action on the tenant.
  - An empty workspace id is still refused: everything is off, and a setting is at its floor.
- **Audit:** `capability_called` and `approval_asked` name no workspace for a tenant-wide call (`workspace: null`), and portalr's admin words them as "on the tenant". grantr stores no workspace as `""`, as its integrations and settings tables already do, so nothing migrates.
- **The providers refuse the mismatch.** artifactr's and reflexr's providers raise `ValueError` for one of their workspace commands called with no workspace. grantr's and portalr's handlers read only the tenant.
- **`lattice_core.approvals`** moves to 1.1.0 too, since its schema embeds `Scope`.

## Options considered

### Option A: Commands declare tenant-wide; no workspace is the tenant (chosen)

**Pros:** where a call is checked is declared once, beside the command, and the parity test and portr read it from the catalog. A grant, an integration or a setting in one workspace never decides a tenant-wide call. portr asks a client for a workspace only where a command needs one.
**Cons:** every implementation of the ports, and every fake in the tests, takes `str | None`. The schemas only widen, so the contracts move to 1.1.0, and `lattice:breaks` finds no break, but an application's own `Integrations`, `Settings` or provider must now accept None: the change is marked breaking for it.

### Option B: A reserved workspace id for the tenant

**Cons:** every store, URL and check would have to know the reserved id. A workspace could be made with it, and nothing in the types would say which calls may use it.

### Option C: portr picks a workspace for tenant-wide calls

**Cons:** the call would be checked where the client happened to be, not on the tenant, as portalr's calls were. A person with a role in one workspace could list every workspace, and the audit would name a workspace that played no part.

## Consequences

- Easier: portr's MCP server offers tenant-wide tools with no workspace argument, and a client finds a workspace with `artifactr_list_workspaces` before anything else.
- Easier: grantr's and portalr's commands are checked on the tenant, as their routes always were.
- Harder: `Integrations`, `Settings`, grantr's `Holds` and every implementation of them take a workspace that may be None. An application that implements one narrows its own.
- To revisit: a tenant-wide command whose handler needs a workspace is a mistake the catalog doesn't catch, since its route doesn't name one; the provider's tests catch it.
