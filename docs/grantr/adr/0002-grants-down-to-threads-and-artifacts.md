# ADR-0002: Grants down to threads and artifacts

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Records decision D2 of [lattice RFC-0001][rfc], identity and access.

## Context

A grant binds a role to a subject on a resource. The coarsest useful grantr stops at the workspace; people also ask to keep one thread or artifact from some of a workspace's members, which needs grants on items and a way for the libraries to leave hidden items out of every read.

## Decision

- **A grant's resource** is the deployment, a tenant, a workspace, or a thread, artifact or rule in a workspace.
- **A grant on an item adds to the workspace's grants;** on a restricted item ([ADR-0003](0003-visible-to-the-workspace-unless-restricted.md)), it is the only kind that applies.
- **A second hook, `hidden`,** returns the threads and artifacts an actor may not see in one workspace, and artifactr filters every read path with it.

## Options considered

| Option | For | Against |
|---|---|---|
| **Down to threads and artifacts, with `hidden` beside the check (chosen)** | Covers the requests people make, in v0.1 | Every read path in artifactr has to filter, and missing one leaks an item |
| Tenant and workspace only, with threads and artifacts later | A smaller v0.1 | A second breaking change to the hooks later |

## Consequences

- Easier: one thread can be kept from part of a workspace without a new workspace.
- Harder: phase 5 needs a test per read path, since the permission-matrix test checks that a surface asks, not that it filters.

[rfc]: ../../rfcs/0001-grantr-identity-and-access.md#decisions
