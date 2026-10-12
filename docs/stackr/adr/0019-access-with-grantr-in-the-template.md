# ADR-0019: Access with grantr in the template

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Amends [ADR-0002](0002-local-supabase-through-its-cli.md) and [ADR-0011](0011-the-application-template-in-detail.md): the tenant is no longer in the token. Builds phase 4 of [lattice RFC-0001](../../rfcs/0001-grantr-identity-and-access.md).

## Context

A generated application read its user's one tenant from `app_metadata.tenant_id` in their Supabase token, and let every user of a tenant do anything in it: the libraries had no hook that heard the action until lattice RFC-0001's phase 1. grantr (phases 2 and 3) now holds tenants, members, roles and keys, and answers the libraries' `authorize` hook.

## Decision

- **An `access` question, `grantr` by default.** `none` keeps the token's tenant claim and no hook, as before.
- **The token says who, the request says where.** With grantr, a request names its tenant in `X-Tenant`, or a WebSocket in its `tenant` query parameter; a user who is a member of one tenant may leave it out. A caller not in the tenant is 403, and a user in several who names none is 400.
- **A service principal's key stands in for a token,** in the same `Authorization: Bearer` header: a credential that begins `grantr_sk_` is a key, and belongs to its tenant.
- **Both libraries' `Workspaces` take `grants.hooks(subject_of).authorize`.** `access.py` maps each library's actors to grantr's subjects: a person, and an agent or client acting for one, as that person; the system, evaluators and the application's code rules as the application's own principal, which `Grants.bootstrap()` grants `application` when the application starts; a client with a key as its principal.
- **The deployment's own commands are `{slug}-admin`**, which `make operator`, `make tenant` and `make migrate-tenants` run (grantr ADR-0021). They take a user's email, looked up with `AUTH_SERVICE_ROLE_KEY`, or their id.
- **`access.md` is committed in every application with grantr:** every role against every action, which a test of the application compares with `grantr.testing.matrix`. The template renders it for the libraries an application chose, and `stackr:access-matrix` checks the template's against the libraries in each pull request.
- **reflexr's `ExternalAgentActor` gains `on_behalf_of`,** as artifactr's has: a person's MCP client is checked as them in both libraries.

## Options considered

| Option | For | Against |
|---|---|---|
| **grantr by default, `none` to keep the token's tenant (chosen)** | New applications start with access closed by default | A second variant for the template's checks |
| grantr always | One variant | An application that doesn't need roles carries grantr |
| **Keys in `Authorization: Bearer` (chosen)** | One header for every caller; the MCP servers' guard checks both | A token and a key are told apart by their prefix |
| A header of their own, such as `X-Api-Key` | Explicit | Every surface, the WebSocket and the MCP guard read two headers |

## Consequences

- Easier: an application's members, roles and keys are managed through grantr's API, and a change to a library's actions or a role shows in `access.md`.
- Harder: a client of a user in several tenants names one, and an application that moves to grantr runs `make migrate-tenants` once.
