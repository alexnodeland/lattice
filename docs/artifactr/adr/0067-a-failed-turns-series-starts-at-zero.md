# ADR-0067: A turn's failed series starts at zero

**Status:** Accepted
**Date:** 2026-10-13
**Deciders:** Alex Nodeland

## Context

`artifactr.turns` counts turns by trigger and outcome. A series exists from its first sample, and Prometheus's `increase` and `rate` count from a series' second sample: the first is where the series starts, not an increase. So the first failed turn of a tenant, a workspace and a trigger, after a deploy or ever, counts as none. portalr's admin counts a tenant's failed turns from this series (portalr ADR-0023), and showed 0 after a single failure.

A counter's labels must be known to record a zero for them. `artifactr.runs` carries a failure's reason, a free string known only when the run fails. `artifactr.turns` carries the trigger, known as the turn starts, and the outcome, one of four.

## Decision

- **As a turn starts, the `Runner` adds zero to its `failed` series:** the same tenant, workspace and trigger, outcome `failed`. A failure then increases a series that already exists, and is counted.
- **Only `failed` is started so:** it is the series that is read for its increase. Counting completed or paused turns doesn't depend on their first.
- **`artifactr.runs` is unchanged:** a failure's reason isn't known before it fails. Failed turns are read from `artifactr.turns`.

## Options considered

| Option | For | Against |
|---|---|---|
| **Add zero to the failed turn series as a turn starts (chosen)** | Its labels are known; one add per turn; any reader of the series counts the first failure | A series per tenant, workspace and trigger exists before any failure |
| Add zero to `artifactr.runs`' failed series | The runs metric | Its reason isn't known until the run fails |
| Prometheus's created-timestamp zero ingestion | No change in artifactr | A feature flag on every Prometheus that reads it |

## Consequences

- Easier: an increase of `artifactr.turns{artifactr.turn.outcome="failed"}` over any window counts every failure in it.
- Harder: each tenant, workspace and trigger has a failed series from its first turn, at zero.
