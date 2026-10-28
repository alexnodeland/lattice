# ADR-0035: Every number an agent states traces to a computation

**Status:** Proposed
**Date:** 2026-10-28
**Deciders:** Alex Nodeland
**For:** #998 (quantr), #1020, #1013, #1014

## Context

With data spaces (#999) and quantr (#998), agents will report pipeline, revenue, forecasts and experiment results that people act on. The commonest failure in agent analytics is a number that was never computed: misremembered, mis-rounded, or invented arithmetic in the reply. People can't tell which figures to trust.

The owner decided (2026-10-28):

- analysis runs in a dedicated kernel;
- typed operations come first, with free code as a fallback;
- numbers are linked to their source and checked before a reply is sent.

## Decision

- **A figure an agent states must come from a computation**: a semantic query result, a typed operation, a code cell or a driver-model output. Each of these produces addressable result cells pinned to snapshots and versions.
- **Every figure in a reply links to its result cell.** Arithmetic on fetched numbers goes through a computation, not into the reply.
- **A checker runs before a reply is sent.**
  - It extracts numeric claims and matches them to referenced results, allowing for rounding and units.
  - Fuzzy matches go through the `decide` port (ADR-0034).
  - It flags unlinked or mismatched figures.
  - The agent must compute, link or correct a flagged figure, or mark it explicitly as an estimate or as supplied by the user.
- **Typed operations come first.**
  - Tested operations with built-in diagnostics are preferred.
  - Free code is allowed, but marked *unverified method*.
  - Statistical hygiene is on by default: intervals, assumption checks, multiple-comparison corrections.
- **Analysis runs in a sandboxed kernel** over policy-filtered, pinned snapshots, with no network.

## Options considered

### Option A: Linked and checked (chosen)

| Dimension | Assessment |
|---|---|
| Trust | High: every figure is traceable, and gaps are flagged |
| Cost | A checker pass per reply that contains numbers |
| Honesty | Estimates are allowed, but labelled |

**Pros:** Changes the agent's behaviour, not just its display.
**Cons:** Adds latency and a fix loop to replies with numbers.

### Option B: Linked, not enforced

| Dimension | Assessment |
|---|---|
| Trust | Medium: links where they happen to exist |
| Cost | Low |

**Pros:** Cheap.
**Cons:** Doesn't stop invented numbers.

### Option C: Strict blocking and regeneration

| Dimension | Assessment |
|---|---|
| Trust | High |
| Cost | High: regeneration loops |
| Honesty | Forbids estimates even when an estimate is the honest answer |

**Pros:** Nothing unlinked ever ships.
**Cons:** Costly loops, and less honest than labelling estimates.

## Trade-off analysis

Links without enforcement don't change what agents do. Strict blocking forbids the honest "roughly" and loops expensively. Linking with a checker that demands a link or an explicit label gives traceability without dishonesty.

## Consequences

- **Easier:**
  - people can click any number to see where it came from;
  - evals can score number fidelity per agent.
- **Harder:**
  - every surface that renders agent text (chat, artifacts, notifications, reports) must carry and render the links;
  - the checker needs a good numeric-claim extractor.
- **To revisit:** whether to extend the rule from numbers to other checkable claims (dates, names of entities).

## Action items

1. [ ] Build result cells in the kernel and query results (#1013, #1005).
2. [ ] Build the checker, with eval sets of invented, mis-rounded and correct numbers (#1020).
3. [ ] Build the typed operations library with diagnostics (#1014).
