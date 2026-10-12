# ADR-0022: A tenant's members list its workspaces

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Amends [ADR-0011](0011-built-in-roles-over-the-catalogs.md) and [ADR-0019](0019-runtime-actions-and-the-application-role.md).

## Context

artifactr lists a tenant's workspaces (`Workspaces.list`, `GET /workspaces`). The listing spans the tenant, so it asks `authorize` for `artifactr:read_workspaces` with no workspace, which grantr checks on the tenant, and then asks `artifactr:open` of each workspace it finds, and leaves out those refused. A workspace's roles don't reach the tenant, so by ADR-0011's prefix rule only a tenant's owners and admins, and the application, could list; a member with roles in two workspaces couldn't list either.

## Decision

- **`member` holds the tenant-wide listings whose results are filtered:** `artifactr:read_workspaces`. What a member sees is what they may open.
- **No workspace role holds it,** though its name begins `read_`: it is asked of the tenant, where they don't apply, so the matrix shows it where it holds.
- **`application` holds it, with every read,** so relayr's start can list the workspaces it follows.

## Options considered

| Option | For | Against |
|---|---|---|
| **`member` holds the filtered listings (chosen)** | Every member lists what they may open | One more action in `member` |
| Owners and admins only | Nothing to change | A member can't find their own workspaces |
| Grant it per workspace | No tenant-level action | Never asked there: the listing is asked of the tenant |

## Consequences

- Easier: `/me` and a UI's workspace list agree for every member.
- Harder: a tenant-wide read that isn't filtered per workspace, such as reflexr's rule definitions, must not be added to `member`; this one is because artifactr filters it.
