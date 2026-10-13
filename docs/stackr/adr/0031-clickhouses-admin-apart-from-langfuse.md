# ADR-0031: ClickHouse's admin, apart from Langfuse

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Amends [ADR-0027](0027-the-single-hosts-backups.md): a new host's ClickHouse is restored as ClickHouse's own admin, not as Langfuse's user with the bucket's keys in the statement. Closes [#140](https://github.com/alexnodeland/lattice/issues/140).

## Context

ClickHouse's image makes the user `CLICKHOUSE_USER` names, gives it every privilege on every database, and removes its own `default` user. stackr named Langfuse's user so. That made Langfuse's credential ClickHouse's admin: the one an operator restored a host with, and one that a compromised Langfuse could use to reach the whole server.

## Decision

- **stackr makes ClickHouse's users itself,** in `deploy/clickhouse/users.xml`, and the image makes none (`CLICKHOUSE_SKIP_USER_SETUP`). stackr now removes the `default` user itself, as the image did.
- **`admin` is the operators':**
  - its password is `CLICKHOUSE_ADMIN_PASSWORD`, which `make env` generates;
  - it signs in from inside the container only;
  - it has every privilege, access management, and the named collections, such as a single host's `backups`. It can't print a collection's secrets.
- **`langfuse` is Langfuse's:**
  - `ALL` on its own database, `default`, where it runs its migrations;
  - `SELECT` on the system tables Langfuse 4.46 reads, and no others: `parts`, `tables`, `columns` and `mutations`, for its migrations, event propagation and native codec; `processes` and `query_log`, where it follows a query's progress and cost;
  - not `system.replicas`, which it reads only on a cluster, nor `system.asynchronous_metrics`, which only its seeding script reads;
  - no other database: it can't make one, or reach another's data.
- **Passwords stay off the data volume.** Every password read from the environment, and the bucket's keys, are marked `hide_in_preprocessed`, so the configuration ClickHouse writes to its data volume holds none of them.
- **The single host's `backup` user** keeps what ADR-0027 gave it, with its system tables narrowed to the three the drill reads: `tables`, `parts` and `disks`.
- **A new host's ClickHouse is restored as `admin`,** through the `backups` collection, so no key is written in a statement.
- **The smoke test checks it all.** Langfuse's worker logs no missing privilege, and Langfuse's user is refused another database. On a single host, `admin` restores the latest backup, as the guide's rebuild does, into a scratch database.

## Options considered

| Option | For | Against |
|---|---|---|
| **Users in a configuration file (chosen)** | Reviewed with the code; the same on one machine and on AWS's state host | A restart to change one |
| Users made in SQL, by an init job | Changed without a restart | One more job, with admin rights, before Langfuse starts |
| The image's user as admin, and a second user for Langfuse | The image's own setup | Langfuse's settings change, and the admin's name is the image's |
| **An explicit list of system tables (chosen)** | Langfuse reads only what it needs | A Langfuse release that reads another table fails until the list grows, which the smoke test catches |
| `SELECT ON system.*` | Never out of step with Langfuse | Every system table, `query_log` of every user's queries among them |

## Consequences

- Easier: Langfuse's credential reaches only Langfuse's data and the system tables it reads.
- Harder: one more password in `.env`, and a list of system tables to keep in step with Langfuse's releases.
- Upgrading: nothing to migrate. `make up` recreates ClickHouse with its new users, and `make env` adds the admin's password. By hand, use the client as `CLICKHOUSE_USER=admin`.
- Next: the AWS recipe's state host makes the same users.
