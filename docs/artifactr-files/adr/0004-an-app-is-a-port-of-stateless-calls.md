# ADR-0004: An app is a port of stateless calls

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

Records the app port of [lattice RFC-0003](../../rfcs/0003-native-files-as-artifacts.md#the-app-port-and-the-worker).

## Context

Only a format's own app reads and writes it faithfully. Agents edit through it, by batches of its commands, and every check-in is read by it for its outline, text, review and fingerprint. The pilot's app is WordCraft, whose headless MCP server speaks stdio only, and which later phases run in a sandboxed worker. Every pull request's tests need an app too, without WordCraft.

## Decision

- **`App` is four stateless calls,** bytes in and bytes out: `apply(source, commands, deadline=)`, `inspect(source, deadline=)`, `render(source, page, scale=, deadline=)` and `commands(query)`. No document stays open between calls, which is what lets a worker spawn a fresh process per job.
- **A deadline is the seconds a call may take,** 30 for an edit by default. A call that can't finish raises `AppFailed`, typed `timeout`, `crashed`, `too_large` or `refused`, as the worker will report a breach.
- **An app names itself:** `name`, `version` and `build`, the image it runs in, which an agent's revision records in its provenance.
- **One adapter per app,** since apps' control channels and commands differ. The WordCraft adapters, `Subprocess` and `Worker`, are phases 2 and 3.
- **`FakeApp` is public,** for applications' tests as well as the package's. Its files are JSON, paragraphs and comments; every save stamps them, as native apps stamp the time, so the bytes change on every save and the fingerprint only when the content does. It can be told to fail in each of the four ways.
- **How much an app can talk,** and which merge strategy it allows, are capabilities of each adapter in RFC-0003. Neither is in the port yet: every app is at the pilot's level, save only, and `lock` is the only strategy, so each waits for an adapter that differs.

## Options considered

### Option A: Stateless calls, with a fake (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: four calls and a typed failure |
| Isolation | A call is a job; a worker needs nothing between jobs |
| Tests | The fake runs everywhere, in microseconds |

**Pros:** the port fits a sandbox with no network and no state.
**Cons:** every call sends the whole file, which phase 2 measures for large documents.

### Option B: A session per document

**Cons:** a document open between calls is state a worker must keep, isolate and clean up; it is phase 5's streamed session, evaluated separately.

## Trade-off analysis

Stateless calls cost bytes on the wire and buy a worker that can be thrown away after every job, which is what the sandbox needs.

## Consequences

- Easier: `NativeFiles` is tested end to end against the fake, on every pull request.
- Harder: the fake is not a fidelity test; phase 2's nightly report compares WordCraft's saves feature by feature.
- Revisit: the port's talk level and merge strategy, with the first adapter that needs them; spans and metrics for `apply`, `inspect` and `render`, with the worker in phase 3.

## Action items

1. [x] `App`, `AppCommand`, `Applied`, `Inspection`, `CommandSpec`, `AppFailed` and `FakeApp`.
