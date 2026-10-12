# ADR-0005: A user's tenants from grantr's memberships

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Records decision D5 of [lattice RFC-0001][rfc], identity and access.

## Context

stackr's template reads a user's one tenant from `app_metadata.tenant_id` in their Supabase token, set by the service role. Moving a user, or letting one belong to two tenants, means changing the token, and anything in a token is stale until it refreshes.

## Decision

- **The token carries who, not where.** The client names the tenant on each request, with an `X-Tenant` header or a `tenant` query parameter on a WebSocket, and the resolver asks grantr whether the user is a member. A user with one membership may omit it.
- **A service principal's key names its tenant,** so a key can't reach another tenant.
- **grantr is the registry of tenants and their members;** Supabase Auth only authenticates.

## Options considered

| Option | For | Against |
|---|---|---|
| **grantr's memberships; the request names the tenant (chosen)** | A user can belong to several tenants, and a change applies at once | A client with several tenants must name one |
| One tenant in the token's `app_metadata` | What the template does today | One tenant per user, and changes wait for a token refresh |
| Roles in the token, through Supabase's access-token hook | No lookup per request | Stale for up to an hour, and the token grows with every workspace |

## Consequences

- Easier: moving a user between tenants, or adding them to a second, is a grant.
- Harder: a breaking change for generated applications, and `make migrate-tenants` moves existing users once.

[rfc]: ../../rfcs/0001-grantr-identity-and-access.md#decisions
