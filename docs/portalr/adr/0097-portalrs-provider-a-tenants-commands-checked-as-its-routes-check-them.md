# ADR-0097: portalr's provider: a tenant's commands, checked as its routes check them

**Status:** Accepted
**Date:** 2026-11-02
**Deciders:** Alex Nodeland
**Implements:** lattice [RFC-0014](../../rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md)'s Tracking item "artifactr, grantr, reflexr, relayr, portalr: their catalogs, providers, ..." for portalr (#916); beside [ADR-0094](0094-portalrs-commands-its-admins-reads-and-the-tenant-and-member-it-makes.md)

## Context

ADR-0094 declares portalr's 14 commands, which only portalr's routes served. portr reaches commands only through lattice-core's registry (lattice ADR-0043), so portalr needs a provider. Its commands are tenant-wide (lattice ADR-0044): the enforcer checks each call's gate on its tenant. Three of them are the operators', though, and portalr's routes check those on the deployment:

- the deployment's tenants;
- its links;
- creating a tenant.

A deployment role puts no one inside a tenant, so the enforcer's check on the tenant would refuse an operator.

## Decision

- **`portalr.capabilities.PortalrProvider(grants, readers, *, invite=None)`** is lattice-core's `Provider` and `Commands` for the tenant's 11 commands:
  - telemetry: traces, logs, metrics, scores, feedback and adoption;
  - spend and usage;
  - inviting a member, offered only where an `invite` is given.
- **Each call is checked as the routes check it, before a reader is asked.** Only then does the provider make the reader's `Tenant`, as the router does; the test that only the router makes one now names the provider too. The checks:
  - grantr's action on the tenant, as the person the call is for (grantr's `subject_of_call`);
  - for an analytics session's traces, whether they operate the deployment (ADR-0073): a search by one is refused, and a trace is shown without it.
- **It answers what the routes answer, as JSON:** a reader's `Ok`, `Unavailable` or `Unconfigured`; and, for an invitation, the tenant and the user.
- **The operators' commands aren't offered,** and calling one is refused: they stay portalr's admin's until a command can be checked on the deployment.
- **`portalr.commands.ARGUMENTS`** maps each command's name to its arguments model, which the provider validates a call with.

## Options considered

### Option A: The tenant's commands, the operators' left to portalr's admin (chosen)

**Pros:** every call the provider takes is checked where portalr's routes check it, and nothing about operators changes.
**Cons:** a client can't make deployment links or create tenants through portr yet.

### Option B: All 14, the operators' checked by the provider on the deployment

**Cons:** the enforcer's grant step would still check them on the tenant first and refuse an operator. Passing that step would need a deployment scope in lattice-core's `Scope`, a decision of its own.

## Consequences

- Easier: portr offers a tenant's admins portalr's reads and invitations in the `admin` toolset.
- To revisit: a deployment-wide scope for commands, if operators' commands should reach clients.
