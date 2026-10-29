# ADR-0032: Replicated records in DuckLake, so every answer cites a snapshot

**Status:** Proposed
**Date:** 2026-10-28
**Deciders:** Alex Nodeland
**For:** #999 (graphr data spaces), #1003, #1004

## Context

Data spaces replicate sources by default and federate live per dataset when freshness matters or copying isn't allowed (#1003). Replicated data must:

- be fast for analytics (aggregates over millions of rows);
- **reproduce any past answer exactly**, because provenance means nothing if the data under it has changed since;
- honour forgetting: a right-to-be-forgotten request reaches every retained copy;
- run self-hosted in stackr, with as few new services as possible.

## Decision

- **Replicated records are stored in DuckLake** (MIT). Data files are Parquet in Supabase Storage or S3-compatible storage. The catalog is in the knowledge Postgres. It runs in the stackr `knowledge` profile.
- **Every sync commits a snapshot.** Answers, derived datasets, analyses and models cite `snapshot_id`, and queries can read `AS OF` a snapshot.
- **Snapshot retention and compaction are settings for each space.** A snapshot that something cites stays pinned until nothing cites it.
- **Forgetting rewrites the affected files across retained snapshots** and re-derives whatever depends on them. A tombstone with no personal data records the rewrite. Answers that cited a rewritten snapshot are marked *revised*.
- **DuckDB is the execution engine** over DuckLake, and over federated scanners (ADR-0033).

## Options considered

### Option A: DuckLake (chosen)

| Dimension | Assessment |
|---|---|
| Reproducibility | Snapshots and time travel built in |
| Operations | A catalog in the Postgres we already run; files in storage we already run |
| Analytics | DuckDB-native, fast |
| Maturity | Young format |

**Pros:** No new services. Native to the engine we execute on.
**Cons:** A younger ecosystem than Iceberg's.

### Option B: Apache Iceberg

| Dimension | Assessment |
|---|---|
| Reproducibility | Snapshots built in |
| Operations | A REST catalog or Polaris to run |
| Ecosystem | Broadest (Spark, Trino, Snowflake) |

**Pros:** The widest interoperability.
**Cons:** Another catalog service to run and secure.

### Option C: Postgres schemas with bitemporal columns

| Dimension | Assessment |
|---|---|
| Reproducibility | Possible, but costly history |
| Operations | Simplest: one database, row-level security |
| Analytics | Slow at scale |

**Pros:** Nothing new to run.
**Cons:** Analytics are slow, and history at row level costs a lot.

## Trade-off analysis

DuckLake gives Iceberg's snapshot semantics without a new catalog service, and it is native to DuckDB. Postgres schemas are simplest, but fail on analytics and history cost. If interoperability with outside engines becomes a need, DuckLake data can be exported to Iceberg later.

## Consequences

- **Easier:** exact re-runs; time travel; cheap storage; one engine.
- **Harder:**
  - forgetting means rewriting Parquet files across snapshots;
  - retention has to respect pinned snapshots;
  - DuckLake's young format needs pinned versions and upgrade tests.
- **To revisit:** Iceberg export if outside engines need the data.

## Action items

1. [ ] Add DuckLake to the stackr `knowledge` profile (#1004).
2. [ ] Implement snapshot pinning, retention and forgetting rewrites (#1004).
