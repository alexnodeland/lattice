# ADR-0043: Connections: grantr objects, one tenant each, read on every call, revoked at once

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** lattice [RFC-0014](../../rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md)'s Decisions P7 and O12, for #917

## Context

portr serves lattice to outside clients, such as Claude and Cursor, over MCP's OAuth, with Supabase Auth as the authorization server. RFC-0014 makes the result of a person's consent a **connection**: one person, one client, one tenant, and the toolsets the person chose. It is a grantr object, beside keys: listed, audited and revoked like them. Supabase's grants alone can't be revoked at once, since an access token outlives its grant.

Bindings (ADR-0041) set the pattern for a per-tenant object: a table under the tenant policy, commands audited in their transaction, and reads for the deployment.

## Decision

- **`Connection`**, in `grantr.core`, has:
  - an `id`, `con_` and 16 hex digits;
  - its one `tenant`;
  - its `user`, the person as whom every call is checked;
  - its `client`: the OAuth `client_id`, its registered name and its URI, where it has one;
  - its `toolsets`, which always include `core`;
  - `created_at`, `last_used_at` and `revoked_at`.
- **Keys stay keys:** a service principal's key is its own connection (portalr ADR-0024), so a connection is a person's.
- **`Grants.connections()` returns `GrantrConnections`:**
  - **`connect(tenant, client, toolsets=, by=)`:** a person connects a client for themselves, to a tenant they're a member of. Connecting a client again while its connection is live adds the toolsets to it. **`add_toolsets`** does the same for a client that steps up to a toolset and is sent back to the consent page.
  - **`listed(tenant, by=, user=)`:** the connections the caller may read, revoked ones too, oldest first.
  - **`revoke(tenant, id, by=, own_only=)`:** stamps `revoked_at`. The connection is kept, so its history still names it.
  - **`live(tenant, client_id, user)`:** portr's check on every call, so a revoked connection's next call is refused.
  - **`used(connection)`:** notes `last_used_at` at most every five minutes, unaudited, since each call is audited as `capability_called`.
- **Who may, by grantr's ADR-0017 rule that a list is read with the action that changes it:**
  - every member of a tenant holds the two new actions, `grantr:read_connections` and `grantr:revoke_connection`, for their own connections;
  - whoever holds `grantr:add_member` on the tenant, its owners and admins, reads and revokes every connection there, since whoever manages the members manages what they connected;
  - connecting needs `grantr:read_connections`, which every member holds, and no action of its own. Calls through a connection are checked against the person's grants anyway.
- **Audited:** `connection_made`, `connection_toolsets_added` and `connection_revoked`, each naming the person and the client.
- **A member's connections go with them,** as their keys do, and a tenant's with it.
- **`grantr_connections`** (migration 0010) is keyed by tenant and id. The person and the client are columns, indexed after the tenant for portr's check, and the connection is stored as JSON. It is under the tenant policy every table has.
- **The admin API:** `GET /tenants/{tenant}/connections` (`user=` for one person's) and `DELETE /tenants/{tenant}/connections/{id}`. Making a connection is portr's consent API, which calls `connect`.
- **Commands:**
  - `grantr.list_connections`;
  - `grantr.revoke_connection`, which revokes only the caller's own;
  - `grantr.revoke_member_connection`, another member's, which is `admin_high` as RFC-0014 asks. A risk class is fixed per command, as for `grantr.grant_on_tenant`.

## Options considered

### Option A: A grantr table per tenant, read on every call (chosen)

**Pros:** revoking stops the next call; a connection is listed, limited and audited where keys and grants are; row-level security keeps it to its tenant.
**Cons:** a read on every call through portr, which an index after the tenant keeps to one lookup.

### Option B: Supabase's OAuth grants alone

**Cons:** a revoked grant leaves its access token valid until it expires; Supabase knows no tenant or toolset; grantr's audit wouldn't see consent.

### Option C: A separate action for an admin's reach over others' connections

**Cons:** a third action that every role holding `grantr:add_member` would hold anyway, and one more line in every custom role.

## Consequences

- Easier: portr checks a token's `client_id` and `sub` against a live connection, and portalr lists a person's connections and a tenant's in one place.
- Harder: every call through portr reads a connection, and `last_used_at` is minutes behind by design.
- To revisit: per-connection limits, which portr counts (RFC-0014 P12); the connections pages in portalr; revoking the Supabase grant beside the connection, which portr does as it revokes one.
