# ADR-0001: Docker Compose first, with profiles

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

The stack serves local development and single hosts first, and production clusters later. It has many services (database platform, gateway, observability, Langfuse, the application), and not every task needs all of them.

## Decision

- **Docker Compose** is the first deployment format, as one project with **profiles**: `gateway`, `observability`, `langfuse` and `app`. Supabase runs through its CLI beside it ([ADR-0002](0002-local-supabase-through-its-cli.md)).
- **Images are pinned,** secrets come from a generated `.env`, and CI validates every configuration without starting containers. A separate smoke job starts the core profiles.
- **Kubernetes (Helm) and Terraform** come later, generated or maintained from the same service configuration.

## Consequences

- Easier: one command per profile, and the same configuration in development and on a single host.
- Harder: Compose alone does not scale out; the later targets address that.

## Action items

1. [ ] Implement RFC-0001 phases 0 to 4.
