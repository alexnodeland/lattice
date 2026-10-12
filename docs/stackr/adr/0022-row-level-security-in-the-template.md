# ADR-0022: Row-level security in the template

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

Lattice RFC-0001's phase 6 gives artifactr's, reflexr's and grantr's SQL storage an option for PostgreSQL's row-level security: each transaction names its tenant, the policies the migrations create keep it to that tenant's rows, and the reads that span tenants run on a second engine, as the tables' owner ([grantr ADR-0026](../../grantr/adr/0026-row-level-security-under-the-scoping.md)). The policies hold only a role that doesn't own the tables, so an application that turns the option on needs two roles: the owner, which migrates and reads across tenants, and a role that owns nothing, which does the rest. The template has one URL, `DATABASE_URL`, and connects as Supabase's `postgres`, the tables' owner.

## Decision

- **`DATABASE_ADMIN_URL` turns it on.** With it, the application migrates as that URL's role, the tables' owner, and works as `DATABASE_URL`'s, with the option on in every library and the owner's engine for the reads across tenants. Without it, nothing changes: one engine, as before. Both engines live in `database.py`'s `Database`.
- **The role that owns nothing is `DATABASE_URL`'s user, with its password,** such as `postgresql+asyncpg://{package}_app:…@…/postgres`. One setting says who the application is and how it signs in, so there is no second place to keep in step.
- **The running service keeps the owner's URL,** for the reads across tenants (grantr's keys and memberships, reflexr's scheduler and dispatcher) and for the migrations it runs as it starts.
- **It refuses to work as a role the policies don't hold.** `DATABASE_URL` and `DATABASE_ADMIN_URL` naming the same user is refused when the database opens, and at startup the application checks that its role is no superuser, doesn't bypass row-level security, and neither owns the schema nor is a member of its owner's role, whose ownership it would inherit.
- **`make db-roles` creates that role, or sets its password,** as `DATABASE_ADMIN_URL`'s role, before the application first starts: `{slug}-admin db-roles`, with access by grantr, on PostgreSQL only. The name is quoted as `grant()` quotes it, and the password is sent as a SCRAM-SHA-256 verifier computed in the process, never in the clear, so neither an error, `pg_stat_statements` nor DDL logging holds it; the password must be printable ASCII, which PostgreSQL's SASLprep leaves as it is; a refusal is reported without the statement. It refuses a role that is a superuser, bypasses row-level security or owns the schema, and the owner's own user. Migrations hold no secrets: each library's `migrate(application_role=...)` grants the role by name, its tables, their sequences and the schema, each time the application starts. The order is: create the role, then start.
- **The smoke test is the exit criterion.** `make smoke-app` runs the application on local Supabase with both URLs, and, past the libraries' scoping, checks that every table has row-level security and a policy, and that the application's sessions are the role that owns nothing; then, past the libraries' scoping, reads the tables as that role: with no tenant, it sees no rows; in another tenant, none of the first's, nor can it write one; and the triage agent's run, which the scheduler finds across tenants, still succeeds.

## Options considered

| Option | For | Against |
|---|---|---|
| **The role from `DATABASE_URL`, made by an admin command (chosen)** | One place for the name and password; migrations hold no secrets | A command to run before the first start |
| Migrations create the role | Nothing to run | A password in migration logic, and a migration that needs to create roles |
| A third role with `BYPASSRLS` for the reads across tenants | The RFC's words | A third role and password, and `BYPASSRLS` needs a superuser to grant ([grantr ADR-0026](../../grantr/adr/0026-row-level-security-under-the-scoping.md)) |

## Consequences

- Easier: a query a library scoped wrongly still sees no other tenant's rows in a deployment with both URLs.
- Harder: such a deployment has two database URLs, and runs `make db-roles` before it first starts, and again when the password changes.
- Harder: the template without access by grantr wires the option, but has no `db-roles` command: an application there creates its role itself.
- Harder: the owner's credentials live in the application's process, so row-level security guards against a query scoped wrongly, not against a compromised application.
