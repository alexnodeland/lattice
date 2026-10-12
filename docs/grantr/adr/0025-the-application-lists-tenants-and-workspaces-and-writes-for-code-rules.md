# ADR-0025: The application lists tenants and workspaces, and writes for its code rules

**Status:** Accepted, amended by [ADR-0027](0027-the-application-installs-the-rules-people-accept.md)
**Date:** 2026-10-12
**Deciders:** Alex Nodeland
**Amends:** [ADR-0019](0019-runtime-actions-and-the-application-role.md), the `application` role's actions, and [ADR-0021](0021-the-deployments-own-tools.md), the deployment's own tools

## Context

stackr's template wires relayr in (relayr's phase 3). At startup, relayr follows every workspace of every tenant the application serves. It lists the tenants, then each tenant's workspaces through artifactr's `Workspaces.list`, which asks `artifactr:read_workspaces` of the tenant. Rules defined in code run as the application ([ADR-0020](0020-the-rule-role.md)). Through relayr's outbound adapter they write in artifactr: they propose changes, post notices, and, where their allowlists say, create artifacts and threads and make keyed edits ([relayr ADR-0022](../../relayr/adr/0022-what-a-rules-actor-needs-in-artifactr.md)). `Grants.tenants(by=)` is an operator's, and the `application` role held none of artifactr's writes.

## Decision

- **`application` holds `artifactr:read_workspaces`.** It lists only the workspaces it may open, which are all of them. It already held it, as every read but portalr's admin reads; a test now holds it to that.
- **`application` holds what code rules write in artifactr:** `artifactr:propose_change`, `post_message`, `create_artifact`, `edit_artifact` and `create_thread`. The template maps a code rule's actor in artifactr, `reflexr:<code rule>`, and an agent turn acting for it, to the application's principal. relayr's per-rule allowlist still limits each rule to what it grants.
- **It holds nothing else of a person's:** no `respond_to_proposal`, no `archive_artifact`, and no rule management. Stored rules write as their own principal, with `rule` and an artifactr-side role granted apart (lattice RFC-0001's phase 5).
- **`Grants.served_tenants()` lists every tenant, checking no one,** for the deployment's own in-process tools, as `provision_tenant` is. No surface reaches it. `tenants(by=)` stays the operator's, for the admin API. A name of its own keeps a call that forgets `by=` from listing every tenant.
- **The application sees every restricted item ([ADR-0024](0024-who-sees-a-restricted-item.md)), and so code rules can edit restricted artifacts.** That follows from the application acting for the deployment: its rules are the deployment's own code, reviewed as code.

## Options considered

| Option | For | Against |
|---|---|---|
| **Code rules' writes in `application` (chosen)** | One grant, made at start, covers every tenant; code rules are the application's own code | The application's principal can write in every workspace |
| A role per code rule, granted in each tenant | Each rule holds only what it writes | A grant per rule in every tenant, made as each is created |
| **A separately named no-check list (chosen)** | No call can bypass the operator's check by forgetting `by=` | Two methods that list tenants |
| `tenants(by=None)` for the tools | One method | A missing argument would list every tenant to anyone |

## Consequences

- Easier: relayr's followers find every workspace at startup, and code rules act in artifactr with no grant to make per tenant.
- Harder: the application's principal holds artifactr writes in every tenant, so relayr's allowlists are the limit between one code rule and another.
