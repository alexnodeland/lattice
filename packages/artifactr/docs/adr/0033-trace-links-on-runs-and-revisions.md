# ADR-0033: Trace links on runs and revisions

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

[RFC-0002](../rfcs/0002-observability-feedback-and-evaluation.md) has a run record the OpenTelemetry trace id of each attempt, so that feedback on a turn or an artifact version can be attached to the trace it is about, and says SQL storage adds a migration for it. Three details were left open:

- **Where the trace id comes from.** Core is sans-IO ([ADR-0001](0001-python-library-with-sans-io-core.md)) and knows nothing of OpenTelemetry. The agent layer knows the trace of each attempt, because its `wrap_run` runs inside it.
- **Which attempt wrote an artifact version.** A run that pauses on a question and resumes runs twice, in two traces. Feedback on a version the first attempt wrote belongs to the first trace, and nothing in a run tells the attempts' writes apart.
- **The migration.** SQL storage keeps runs and revisions as the JSON of their Pydantic models ([ADR-0021](0021-sql-storage.md)), beside only the columns that reads filter on.

## Decision

- **`run_started` carries the attempt's trace id**, set by the agent layer when the run is traced. Core appends it to `Run.trace_ids`, oldest first, and keeps the list across pauses and ends. The log therefore holds every link, and the run entity stays derivable from the log.
- **A revision carries the trace it was committed in** (`Revision.trace_id`), stamped by the workspace from the current span when it saves the revision, as it stamps an outcome's `seq`. Feedback on a version then finds its trace directly, whichever attempt, surface or person wrote it.
- **No migration.** Both fields live in the stored JSON and default to empty for rows written before them. No read filters on them, so they get no columns; a migration would change nothing. If a lookup from a trace to its run is needed later, it gets a table and a migration then.

## Options considered

| Option | Precise for resumed runs | Schema change |
|---|---|---|
| **Trace ids on `run_started` and revisions, in JSON (chosen)** | Yes | None |
| Trace ids on runs only | No: a version maps to a run, not an attempt | None |
| A `trace_ids` column on `artifactr_runs` | No | A redundant copy of the JSON |
| A trace id on every envelope | Yes | None, but finding the event for a version or message means scanning the log |

## Consequences

- Easier: turn feedback goes to the run's traces and artifact feedback to the exact trace of the write, with no extra reads.
- Easier: clients see trace ids in the log and in revisions, and can link to them.
- Harder: `trace_id` is a field a host sets on a core model, like `seq` on outcomes; hosts other than `Workspace` must stamp it themselves.

## Action items

1. [x] `run_started.trace_id` and `Run.trace_ids`, with conformance cases.
2. [ ] The agent layer sets the trace id, and the workspace stamps revisions (RFC-0002 phase A1).
