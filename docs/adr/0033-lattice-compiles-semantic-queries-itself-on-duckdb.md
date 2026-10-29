# ADR-0033: lattice compiles semantic queries itself, on DuckDB

**Status:** Proposed
**Date:** 2026-10-28
**Deciders:** Alex Nodeland
**For:** #999 (graphr data spaces), #1005; beside [ADR-0031](0031-data-space-models-in-apache-ossie-with-a-lattice-extension.md) and [ADR-0032](0032-replicated-records-in-ducklake.md)

## Context

Ossie models declare and don't query (ADR-0031), so something has to turn a question into SQL. Letting an LLM write SQL against raw tables gives double counting, wrong joins, no permissions and no reproducibility.

Whatever compiles the query must also:

- apply **permissions intersected**: row and column policies AND the data space ACL, with `req_acls` carried on results;
- attach **provenance**: model, mapping and extension versions, the compiled SQL, snapshot, sync time and quality status;
- use the **ontology mapping** for hybrid graph and records plans;
- target **DuckLake snapshots** (ADR-0032), **live federation**, and **warehouse push-down** (#1026).

## Decision

- **lattice owns the compiler.** A typed semantic query `{metrics, dimensions, filters, time: {grain, range}, order, limit, as_of}` is validated against the model and compiled to SQL. Join paths come from `relationships`, with fan-out protection. Semi-additive and derived metrics, time spines and grains come from the `LATTICE` extension.
- **Execution is on DuckDB** over DuckLake and federated scanners. For warehouses, the compiler emits the warehouse's dialect and pushes the query down.
- **Governed read-only SQL** is the escape hatch. It runs over the model's datasets as views, never over raw tables, and is parsed and rewritten to apply policies.
- **Permissions and provenance are injected by the compiler on every path.** No path reaches data around it.
- **We borrow from `duckdb-ossie` where it fits**, but don't depend on it for semantics.

## Options considered

### Option A: Own compiler on DuckDB (chosen)

| Dimension | Assessment |
|---|---|
| Control of permissions and provenance | Full |
| Ontology hooks | Native |
| Effort | High: metric semantics are subtle |

**Pros:** One place enforces everything. The model in lattice is the truth.
**Cons:** We build and test metric semantics ourselves.

### Option B: Adopt Cube Core

| Dimension | Assessment |
|---|---|
| Control | Partial: Cube's own model and access control |
| Maturity | High: SQL, REST, GraphQL and MCP APIs, with caching |
| Effort | Medium |

**Pros:** Mature and fast.
**Cons:** Cube's model becomes the truth. Intersected permissions, provenance and ontology alignment sit outside lattice.

### Option C: Adopt dbt MetricFlow

| Dimension | Assessment |
|---|---|
| Control | Partial |
| Metric semantics | Strong |
| Effort | Medium, plus dbt project structure |

**Pros:** Proven metric semantics.
**Cons:** Ties models to dbt's structure and runtime, outside lattice's permissions and provenance.

## Trade-off analysis

The things that make answers trustworthy (permissions intersected, provenance and ontology alignment) have to sit where the SQL is made. With Cube or MetricFlow, those would wrap a black box, and the model would live in two places. The cost of Option A is building metric semantics, which a test suite of known answers bounds (#1005).

## Consequences

- **Easier:** one enforcement point; provenance by construction; hybrid plans; the Postgres-protocol endpoint (#1030) reuses the same compiler.
- **Harder:** we own correctness for fan-out, semi-additive metrics, fiscal grains and dialects. That needs a large known-answer suite.
- **To revisit:** if Ossie publishes a query specification, align the typed query with it.

## Action items

1. [ ] Build the compiler and its known-answer suite (#1005).
2. [ ] Add a property test that no policy can be bypassed through a view (#1005).
3. [ ] Add warehouse dialects and push-down (#1026).
