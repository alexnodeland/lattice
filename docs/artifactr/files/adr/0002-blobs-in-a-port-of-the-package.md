# ADR-0002: Blobs in a port of the package

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

Records [lattice RFC-0003](../../rfcs/0003-native-files-as-artifacts.md)'s D2.

## Context

A native file's bytes can't be in its artifact's data, which every revision, event, replay and bridged event carries ([artifactr ADR-0072](../../artifactr/adr/0072-native-files-are-manifests-over-json-patch.md)). They need a store, keyed so that a blob's access is its artifact's, and kept consistent with the log that names them.

## Decision

- **A port in the package, `Blobs`:** `put`, `get` and `collect`, with `InMemoryBlobs` and `SqlBlobs`. Methods on artifactr's `Storage` would break every storage an application wrote, and nothing else in artifactr needs bytes.
- **The key is `(tenant, workspace, artifact, sha256)`,** as artifactr's keys start. A manifest that names another artifact's digest finds nothing. Revisions of one artifact share its unchanged bytes; bytes are never shared across artifacts or tenants, which would tell an uploader that someone else has a file.
- **The digest and size are the store's,** computed as the bytes arrive, never a client's. A blob is 25 MiB at most by default, up to 100 MiB if the store is told; larger bytes are refused with `TooLarge` as they arrive, before they are all read.
- **In SQL, `artifactr_files_blobs`:** `bytea`, stored `EXTERNAL` since zipped formats don't compress, or SQLite's `BLOB`; the package's own Alembic scripts and version table; row-level security through `lattice_core.sql.tenancy`, as artifactr's storage has it (artifactr ADR-0066). The bytes are loaded only when read, so a put of bytes already there reads none.
- **Put first, then commit.** A put is idempotent by digest, and marks the blob as put now even if it was there. A put never committed is only garbage.
- **Collection.** `collect(scope, referenced, before=)` deletes the workspace's blobs last put before the cutoff that `referenced` doesn't name. `NativeFiles.collect` keeps a day's puts by default (`keep`), and computes `referenced` from every pending proposal's change, then every revision of a native file, archived ones included: in that order, a proposal accepted meanwhile is read as one or the other. The SQL store reads the blobs old enough and deletes the unreferenced ones in batches of 500, each statement checking again that the blob is still that old, so a blob put again meanwhile, for a revision about to be committed, is kept. It runs per workspace, as an actor who sees everything there, and refuses a handle from which anything is hidden.
- **An object store is deferred.** stackr's S3 port, with MinIO by default (stackr ADR-0005), would be the same port with isolation by key prefix. It waits for a deployment that hits the size limit.

## Options considered

### Option A: A port in the package, on PostgreSQL first (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one table, and the patterns artifactr's storage already has |
| Isolation | Row-level security, and keys that start with the tenant |
| Consistency | Put first, collect later: the gap is safe, not absent |

**Pros:** one database to run, back up and secure; the access of a blob is its artifact's.
**Cons:** bytes in PostgreSQL, which suits files of megabytes and not of gigabytes.

### Option B: Methods on artifactr's `Storage`

**Cons:** breaks every storage an application wrote, for what only this package needs.

### Option C: An object store first

**Cons:** another service to run and secure before any deployment needs it, with isolation by prefix rather than by the database.

### Option D: Deduplication across artifacts

**Cons:** a blob's access would no longer be one artifact's, and across tenants it would leak that a file exists.

## Trade-off analysis

Option A keeps the bytes as isolated as the manifests that name them, in the database that already holds them, and costs a collection pass. Options B and C buy nothing yet, and D trades isolation for space.

## Consequences

- Easier: a blob's access follows its artifact's, with nothing to check twice.
- Harder: two stores to keep consistent; collection must run, and must see the whole workspace.
- Deviation from RFC-0003: it says collection deletes "in one statement". The store deletes in batches, each statement guarded by the blob's `last_put`, so the referenced set, which grows with every revision, never has to fit a database's limit on parameters, and the guard against a blob put meanwhile is the same.
- Revisit: quotas on blob bytes per workspace or tenant (RFC-0003's unresolved questions), and renders, which are a cache with the same key, in a later phase.

## Action items

1. [x] `Blobs`, `InMemoryBlobs` and `SqlBlobs`, with its migration and row-level security; the suite on memory, SQLite and PostgreSQL, a two-tenant test, and a property test that collection deletes exactly what is old and unnamed.
