# ADR-0023: portalr's admin reads

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Amends [ADR-0011](0011-built-in-roles-over-the-catalogs.md).

## Context

portalr's admin (lattice RFC-0002) reads a tenant's telemetry and spend, and an operator's view of the whole deployment. Its catalog names them `portalr:read_telemetry`, `portalr:read_spend` and `portalr:read_deployment`. By ADR-0011's prefix rule, every `read_` action lands in `viewer` and above, in a workspace's `admin`, and in `application`, and a tenant's `owner` holds every action but the operator's: so a workspace's viewer could read a tenant's spend, and a tenant's owner the deployment's telemetry.

## Decision

- **A tenant's telemetry and spend are its owners' and admins' to read:** `portalr:read_telemetry` and `portalr:read_spend` are held by a tenant's `owner` and `admin`, and by no workspace role and not `application`, whatever their prefix.
- **The deployment's telemetry is its operators':** `portalr:read_deployment` is held by `operator` alone, and not by a tenant's `owner`.
- **They are named sets in grantr,** `TENANT_ADMIN_READS` and `DEPLOYMENT_READS`, as `EDITOR_COMMANDS` and `FEEDBACK` are: with `MEMBERS_READS` ([ADR-0022](0022-a-tenants-members-list-its-workspaces.md)) they are the reads asked of a tenant or of the deployment, which no workspace role holds.

## Options considered

| Option | For | Against |
|---|---|---|
| **Named sets, placed by role (chosen)** | Each read is held where it is asked, and the matrix shows it | grantr names portalr's actions before portalr's catalog exists |
| The prefix rule | Nothing to name | A workspace's viewer reads the tenant's spend |
| portalr's admin checks its own roles | No change to grantr | Two places that decide access, which lattice RFC-0001 rules out |

## Consequences

- Easier: portalr's admin asks grantr, and its tiles show what the caller may read.
- Harder: portalr's catalog must use these names; the root role-names test holds them until its constant exists, and then against it.
