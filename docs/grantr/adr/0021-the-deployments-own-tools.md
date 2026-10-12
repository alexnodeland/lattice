# ADR-0021: The deployment's own tools

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

stackr's template gains `make tenant`, `make operator` and `make migrate-tenants` (lattice RFC-0001's phase 4). Each runs in process, with the application's database, and with no one signed in. `create_tenant` needs an operator. An application that moves to grantr has users whose tenant was a claim in their token, and who could each do anything in it.

## Decision

- **`Grants.provision_tenant(tenant, *, owner, admins=())`** creates a tenant with its owner, and makes each of `admins` a member and a tenant `admin`, in audit entries made by no one. It changes nothing if the tenant exists, so it can run again. Only in-process tools call it: the router can't reach it.
- **`make operator EMAIL=...`** calls `first_operator`.
- **Each target takes an email, looked up through Supabase Auth's admin API, or a user's id,** so a test or a smoke test can pass the id without the service role's key.
- **Migration keeps what users could do.** `make migrate-tenants` makes each tenant's earliest user its owner, and the rest its admins, and prints who got what; owners narrow it afterwards.
- **Creating a tenant's gateway team stays stackr's `make tenant`.** The `on_tenant_created` callback lattice RFC-0001 designs is deferred: the template's gateway keys are settings today, and phase 4 doesn't need it.

## Options considered

| Option | For | Against |
|---|---|---|
| **An in-process path made by no one (chosen)** | Like `first_operator`: audited, and out of every surface's reach | One more method beside `create_tenant` |
| The tools act as an operator | One path | The tools would need an operator's identity, and a new deployment has none |
| **Migrated users as owner and admins (chosen)** | No one loses what they could do | Every migrated user can manage access until an owner narrows it |
| Migrated users as members | Least access | A migrated application opens empty for everyone |

## Consequences

- Easier: a new deployment is set up with three commands, and an existing one moves without locking anyone out.
- Harder: a migrated tenant starts with broad access, which its owner reviews.
