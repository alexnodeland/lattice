# ADR-0031: ClickHouse's admin, apart from Langfuse

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Amends [ADR-0027](0027-the-single-hosts-backups.md): a new host's ClickHouse is restored as ClickHouse's own admin, not as Langfuse's user with the bucket's keys in the statement. Closes [#140](https://github.com/alexnodeland/lattice/issues/140).

## Context

ClickHouse's image makes the user `CLICKHOUSE_USER` names, and gives it every privilege on every database. stackr named Langfuse's user so, which made Langfuse's credential ClickHouse's admin: the one an operator restored a host with, and one that a compromised Langfuse could use to reach the whole server.

## Decision

- **stackr makes ClickHouse's users itself,** in `deploy/clickhouse/users.xml`, and the image makes none (`CLICKHOUSE_SKIP_USER_SETUP`). The image's passwordless `default` user is removed.
- **`admin` is the operators':**
  - its password is `CLICKHOUSE_ADMIN_PASSWORD`, which `make env` generates;
  - it signs in from inside the container only;
  - it has every privilege, access management, and the named collections, such as a single host's `backups`.
- **`langfuse` is Langfuse's:** `ALL` on its own database, `default`, where it runs its migrations, and `SELECT` on the system tables, which its background migrations read (`system.parts`). It can't make another database or reach another's data.
- **A new host's ClickHouse is restored as `admin`,** through the `backups` collection, so no key is written in a statement.
- **The single host's `backup` user** keeps what ADR-0027 gave it.

## Consequences

- Easier: Langfuse's credential reaches only Langfuse's data.
- Harder: one more password in `.env`.
- Next: the AWS recipe's state host makes the same users.
