# ADR-0031: Data space models in Apache Ossie, with a full `LATTICE` extension

**Status:** Proposed
**Date:** 2026-10-28
**Deciders:** Alex Nodeland
**For:** #999 (graphr data spaces), #1001

## Context

graphr's records memory (#999) brings CRMs, billing, support and warehouses in as **data spaces**. Agents ask typed questions of them, so each data space needs a semantic model: datasets, fields, relationships and metrics, tied to graphr's ontology.

Apache Ossie (incubating; formerly Open Semantic Interchange, OSI) is the emerging open format for semantic models, backed by Snowflake, dbt Labs, Salesforce, Databricks and more than 50 others. As of core spec 0.2.0.dev0:

- **It declares and doesn't query.** The spec says it "does not define a query interface".
- **Its schema is still changing.** The spec says "do not depend on this version in production", and 0.2.0.dev0 breaks 0.1.1.
- **It lacks what reliable answers need:**
  - metrics can't reference metrics, and fields can't reference fields;
  - no additivity, so semi-additive balances such as MRR can't be expressed;
  - no hierarchies, time spine or grains;
  - no row or column policies;
  - no quality rules, provenance or verified queries;
  - `ai_context` holds only instructions, synonyms and examples.
- **It has an ontology module** (`concept`, `identify_by`, `iri`) and standalone mapping documents. Upstream parser support for the mapping documents isn't available yet.

The owner decided (2026-10-28) to model data spaces in Ossie, fill its gaps with a full lattice extension, and not upstream that extension.

## Decision

- **A data space's model is an Ossie document**, with the core spec version pinned. Imports are normalised to the pinned shape, including the old `semantic_model:` array.
- **A `LATTICE` extension carries what Ossie lacks.** It is a versioned JSON Schema in `custom_extensions` (`vendor_name: LATTICE`) and covers:
  - metric semantics (additivity, derived metrics, filters, default grain);
  - time (spine, grains, fiscal calendars, slowly changing dimensions);
  - hierarchies;
  - row and column policies and PII classes;
  - quality checks;
  - verified queries;
  - ownership and provenance.
- **Ossie's ontology module and mapping documents** tie the model to graphr's ontology. lattice implements the mapping-document parser itself.
- **Plain Ossie files import and export losslessly for the core.** Exports keep the extension, or strip it on request.
- **Spec changes go through one versioned adapter**, not through scattered code.
- **We don't upstream the extension.** We'll adopt upstream features as they arrive, mapping them from the extension.

## Options considered

### Option A: Ossie plus a full `LATTICE` extension (chosen)

| Dimension | Assessment |
|---|---|
| Portability | High for the core; the extension is lattice-only |
| Expressiveness | Complete, through the extension |
| Spec risk | Contained in one adapter |
| Complexity | Medium |

**Pros:** It speaks the ecosystem's format (converters for dbt, Snowflake, Databricks and others), and it can express everything reliable answers need.
**Cons:** In practice most of the meaning lives in the extension. Ossie files from other tools carry only the core and need enriching.

### Option B: Ossie plus ODCS data contracts

| Dimension | Assessment |
|---|---|
| Portability | High, with two standards |
| Expressiveness | Quality and ownership covered; metric semantics still missing |
| Complexity | High: two documents to keep in sync |

**Pros:** It uses standards for quality rules, SLAs and ownership.
**Cons:** It still lacks metric semantics, and two files describe one thing.

### Option C: A lattice-native format, with Ossie only for import and export

| Dimension | Assessment |
|---|---|
| Portability | Low by default |
| Expressiveness | Complete |
| Complexity | Medium |

**Pros:** Full control, and no spec churn.
**Cons:** It turns away from the format the ecosystem is converging on.

## Trade-off analysis

Option A keeps lattice's models readable by any Ossie tool and lets lattice import theirs. Only the gaps are lattice-specific. The spec's churn is a real risk; one adapter contains it. Option B doubles the documents and still doesn't solve metric semantics. Option C buys nothing over A except freedom from churn, at the cost of interoperability.

## Consequences

- **Easier:**
  - importing dbt, Snowflake and Databricks models through `apache/ossie-converters`;
  - exporting lattice's models to other tools.
- **Harder:**
  - the extension is ours to maintain;
  - Ossie files from elsewhere answer with less certainty until they are enriched, and lattice must say so.
- **To revisit:** when Ossie 0.2.0 is released, and when its metric language or query specification lands, re-map the extension's overlap onto upstream fields.

## Action items

1. [ ] Publish the `LATTICE` extension's JSON Schema and docs (#1001).
2. [ ] Build the versioned Ossie adapter: parse, validate, normalise, export (#1001).
3. [ ] Build the mapping-document parser (#1002).
