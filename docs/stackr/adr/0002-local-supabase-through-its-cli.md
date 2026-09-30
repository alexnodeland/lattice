# ADR-0002: Local Supabase, through its CLI

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

Applications need PostgreSQL for the libraries' SQL storage, and also authentication, file storage and, later, edge functions, vector indexing and graph queries. Supabase provides these on PostgreSQL and runs locally. The Supabase CLI (`supabase start`) is its official local workflow. A vendored copy of its self-hosting Compose file is the alternative.

## Decision

- The template uses **local Supabase through its CLI**, with a `supabase/` project (configuration and migrations) in the repository.
- The Compose services join Supabase's Docker network. Langfuse and LiteLLM keep their databases on Supabase's PostgreSQL.
- Applications verify **Supabase Auth JWTs** in `resolve_actor`, with the tenant in the token's claims.
- A `make up` runs `supabase start` and the Compose profiles together.

## Options considered

| Option | Maintenance | Features |
|---|---|---|
| **Supabase CLI (chosen)** | Supabase maintains it | Auth, Storage, Realtime, Studio, Edge Functions |
| Vendored self-hosting Compose file | We track Supabase's releases | The same |
| Plain PostgreSQL | Least | Database only |

## Consequences

- Easier: authentication and storage from day one, and a path to hosted Supabase.
- Harder: two tools start the stack, which `make up` hides.

## Action items

1. [ ] Implement RFC-0001 phase 3.
