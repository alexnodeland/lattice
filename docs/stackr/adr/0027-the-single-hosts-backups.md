# ADR-0027: The single host's backups

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Builds the rest of phase 2 of [RFC-0004](../rfcs/0004-hosting-recipes.md): the single host's backups and its restore drill. Records what the RFC left to the build, and where it departs from it.

## Context

RFC-0004 backs up a single host with pgBackRest and ClickHouse's native `BACKUP ... TO S3`, to an S3-compatible bucket off the host, and checks them with a restore drill that a timer runs and Grafana watches. CI runs the drill against MinIO. Building it found that pgBackRest speaks only HTTPS to S3, and the stack's MinIO, which Langfuse uses, serves plain HTTP.

## Decision

### The bucket and its keys

- **The bucket is the `BACKUP_S3_*` settings:** an endpoint reached over HTTPS, path-style, its port, bucket, region and keys. pgBackRest and ClickHouse read the same settings.
- **Its certificate is always checked,** against `BACKUP_S3_CA_FILE`, a CA bundle on the host: the host's own by default, or a store's own CA. pgBackRest names it with `repo1-storage-ca-file`; ClickHouse adds it with `caConfig`, beside the system's, leaving its verification mode as it is, since that setting is global.
- **PostgreSQL's backups are encrypted before they leave the host,** with `aes-256-cbc` and `BACKUP_CIPHER_PASS`, which `make env` generates. Losing it loses the backups: it is kept with the rest of `.env`, off the host. ClickHouse's backups rely on the bucket's own encryption.

### PostgreSQL

- **Built with pgBackRest** (`deploy/host/postgres`), at a pinned package version, from the image `compose.yaml` pins, which `scripts/check-config` holds it to.
- **Its entrypoint** writes pgBackRest's configuration from the settings, readable by `postgres` alone, and turns on WAL archiving only when a bucket is set: without one, nothing would take the WAL, and it would fill the disk.
- **A full backup each Sunday, before the drill, and a differential on the other nights.** pgBackRest keeps two full backups and the differentials and WAL they need, so it can restore to any point in the last one to two weeks. `pgbackrest check` runs first, so a backup fails when WAL archiving does.

### ClickHouse

- **A `backup` user does the backups and the drill,** from inside the container only. It may back up Langfuse's database, use the `backups` named collection and S3, read the system tables, own the drill's databases, and create and fill Langfuse's tables, for a restore onto a new host. Langfuse's own user can't reach the bucket.
- **The named collection's URL and keys come from the environment** (`from_env`), so no key is written in a statement.
- **Each nightly backup is whole,** of Langfuse's database and the drill's, as `clickhouse/<UTC time>`. The bucket's own lifecycle rule expires them.

### The scripts, the timers and the alerts

- **`deploy/host/backup`** (`make backup`; `BACKUP_TYPE` chooses the kind) and **`deploy/host/restore-drill`** (`make restore-drill`) each send their result to the Collector from an exit trap, `stackr.backup.success` and `stackr.restore_drill.success`, 1 or 0, so a run that fails part way still says so.
- **The drill proves the backups restore, with a row written just before.** The latest backups must be under 36 hours old. A sentinel row goes into PostgreSQL, whose WAL is switched and must be archived within two minutes, and into ClickHouse, whose drill database is then backed up. PostgreSQL's latest backup and the WAL since are restored with `docker run`, in a container from the same image with no volume, and must have every table the live databases have, and the sentinel. ClickHouse's latest nightly backup is restored as `restore_drill`, and must have rows in every table where the live one has them; the drill's own backup is restored as `restore_sentinel`, and must have the sentinel; both are dropped first and after.
- **The drill's limits:** each restore checks first that there is room for it, and the waits for recovery and archiving are bounded.
- **systemd timers:** the backups nightly, and the drill each Sunday after them, each with a start timeout. `bootstrap` installs them.
- **Four alerts, provisioned by the host's overlay only:** no backup has succeeded in 36 hours; the latest backup failed; the drill hasn't passed in eight days; the latest drill failed. Before a bucket is set, the first and third fire. No contact point is provisioned: Grafana lists firing alerts, and an operator adds one.

### CI

The single host's run backs up to a MinIO of its own, over HTTPS, with a certificate the job makes and names in `BACKUP_S3_CA_FILE`, so pgBackRest and ClickHouse check it as they would any store's. It waits for MinIO, makes the bucket, runs `make backup restore-drill`, and `make smoke PROFILES=drill` finds the drill's success in Prometheus.

### Where this departs from RFC-0004

- **ClickHouse is restored beside the live database, not into a new container.** The restore reads the same backup a new server would, through the same collection, with no second ClickHouse to configure. It costs the live server, while it runs, the disk of a second copy of Langfuse's database (checked first), the IO to write it, and the memory of the restore. The `backup` user needs `ALL` on the drill's databases, and on Langfuse's, `SELECT`, `BACKUP`, and `CREATE TABLE` and `INSERT` for a restore.
- **CI's drill uses a MinIO of its own, not the stack's.** pgBackRest needs HTTPS, and the stack's MinIO serves Langfuse over HTTP.
- **RFC-0004's design says "full and incremental backups"** and "the latest backups into new containers". The design above is what the host does: weekly full and nightly differential backups for PostgreSQL, a new container for PostgreSQL's restore, and the live server for ClickHouse's. The RFC stays as accepted.

## Options considered

| Option | For | Against |
|---|---|---|
| **A MinIO of the job's own, with a certificate it makes and the recipe checks (chosen)** | The recipe is unchanged: CI fills in `BACKUP_S3_*`, as an operator does | A step of CI scaffolding |
| HTTPS on the stack's MinIO | One MinIO | Langfuse, and every client of the S3 port, move to HTTPS and a private CA |
| Turning certificate checks off for a test bucket | Simplest | A setting that turns security off, one typo from production |
| **ClickHouse restored as another database (chosen)** | No second server, nor its configuration | The restore's disk, IO and memory, on the live server |
| A new ClickHouse container | Apart from the live one | Its users, named collection and disk to set up again |

## Consequences

- Easier: a host's backups and their drill run from timers, are encrypted and checked, and Grafana says when either stops passing.
- Harder: `.env` holds the key to the backups, and has to be kept off the host.
- Harder: ClickHouse's backups are whole each night; the bucket's lifecycle rule has to expire them.
- Revisit: incremental ClickHouse backups, if whole ones grow too large.
