# ADR-0027: The single host's backups

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Builds the rest of phase 2 of [RFC-0004](../rfcs/0004-hosting-recipes.md): the single host's backups and its restore drill. Records what the RFC left to the build, and where it departs from it.

## Context

RFC-0004 backs up a single host with pgBackRest and ClickHouse's native `BACKUP ... TO S3`, to an S3-compatible bucket off the host, and checks them with a restore drill that a timer runs and Grafana watches. CI runs the drill against MinIO. Building it found that pgBackRest speaks only HTTPS to S3: it can relax its check of a certificate, but not turn TLS off. The stack's MinIO, which Langfuse uses, serves plain HTTP, and serving HTTPS would mean HTTPS for Langfuse too.

## Decision

- **The bucket is the `BACKUP_S3_*` settings:** an endpoint reached over HTTPS, path-style, its port, bucket, region and keys, and `BACKUP_S3_TLS_VERIFICATION`, `relaxed` (the certificate is checked) or `none`, for a test bucket with a certificate of its own. pgBackRest and ClickHouse read the same settings.
- **PostgreSQL is built with pgBackRest** (`deploy/host/postgres`), from the image `compose.yaml` pins, which `scripts/check-config` holds it to. Its entrypoint writes pgBackRest's configuration from the settings, readable by `postgres` alone, and turns on WAL archiving only when a bucket is set: without one, nothing would take the WAL, and it would fill the disk. pgBackRest keeps two full backups, with incrementals and the WAL between them, for a restore to any point since.
- **ClickHouse reaches the bucket through a named collection,** `backups`, whose URL and keys come from the environment (`from_env`), so no key is written in a `BACKUP` statement. Langfuse's user may use named collections (`named_collection_control`). Each nightly backup is whole, under `clickhouse/<UTC time>`, and the bucket's own lifecycle rule decides how long they stay.
- **`deploy/host/backup`** runs pgBackRest (full the first time, incremental after), then ClickHouse's `BACKUP`. `stackr-backup.timer` runs it nightly; `make backup` runs it now. It refuses to run without a bucket.
- **`deploy/host/restore-drill`** restores PostgreSQL's latest backup into a new container from the same image, with its own data directory, and requires every table the live databases have; restores ClickHouse's latest backup as the database `restore_drill`, beside Langfuse's, and requires rows in every table where the live one has them, then drops it; and sends `stackr.restore_drill.success`, 1 or 0, to the Collector. `stackr-restore-drill.timer` runs it weekly; `make restore-drill` runs it now.
- **Grafana alerts when the drill hasn't passed in eight days,** from a rule provisioned by the host's overlay only, since a stack on one machine has no drill.
- **`bootstrap` installs both timers,** with the checkout's path.
- **In CI, the single host's run backs up to a MinIO of its own,** started with a certificate the job makes, and `BACKUP_S3_TLS_VERIFICATION=none`. Then `make backup restore-drill`, and `make smoke PROFILES=drill` finds the drill's success in Prometheus.

### Where this departs from RFC-0004

- **ClickHouse is restored beside the live database, not into a new container.** `RESTORE ... AS restore_drill` reads the same backup a new server would, through the same named collection, with no second ClickHouse to configure; the drill drops it after.
- **CI's drill uses a MinIO of its own, not the stack's.** pgBackRest needs HTTPS, and the stack's MinIO serves Langfuse over HTTP.

## Options considered

| Option | For | Against |
|---|---|---|
| **A MinIO of the job's own, with a certificate it makes (chosen)** | The recipe is unchanged: CI fills in `BACKUP_S3_*`, as an operator does | A step of CI scaffolding, and verification off for that bucket |
| HTTPS on the stack's MinIO | One MinIO | Langfuse, and every client of the S3 port, move to HTTPS and a private CA |
| Caddy in front of MinIO, with its own CA | Reuses the edge | A route to MinIO at the edge, on a host, for CI's sake |
| **ClickHouse restored as another database (chosen)** | No second server, nor its configuration | The restore uses the live server's disk while it runs |
| A new ClickHouse container | Apart from the live one, as the RFC says | Its users, named collection and disk to set up again |

## Consequences

- Easier: a host's backups and their drill run from timers, and Grafana says when the drill stops passing.
- Harder: ClickHouse's backups are whole each night; the bucket's lifecycle rule has to expire them.
- Revisit: incremental ClickHouse backups, if whole ones grow too large.
