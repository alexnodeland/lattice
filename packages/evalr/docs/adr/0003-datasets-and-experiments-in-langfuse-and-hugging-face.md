# ADR-0003: Datasets and experiments in Langfuse and Hugging Face

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

Datasets seeded by people's feedback must be versioned, shareable and visible next to the traces they came from. Experiments must score new agents, prompts and models reproducibly. Langfuse is the family's observability backend ([artifactr ADR-0027](https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0027-opentelemetry-observability-with-langfuse.md)), with datasets and experiments of its own. Hugging Face hosts public and private datasets with revisions.

## Decision

- **Langfuse holds working datasets and experiments.** Items have deterministic ids, so syncing is idempotent. Experiments run through Langfuse's experiment API, with the task's spans nested under each item and verdicts as scores.
- **Hugging Face holds published and pinned datasets:** import at a pinned revision, and export with a dataset card recording the source.
- Splits are deterministic by example id.

## Options considered

| Option | Beside the traces | Versioned and shareable |
|---|---|---|
| **Langfuse and Hugging Face (chosen)** | Yes | Yes |
| Files in the repository | No | Through git, awkwardly for large data |
| Langfuse only | Yes | Within one Langfuse project |

## Consequences

- Easier: an experiment's results link to the exact traces and dataset items they scored.
- Harder: two stores to keep in step; ids and revisions make syncing idempotent.

## Action items

1. [ ] Implement RFC-0001 phase 4.
