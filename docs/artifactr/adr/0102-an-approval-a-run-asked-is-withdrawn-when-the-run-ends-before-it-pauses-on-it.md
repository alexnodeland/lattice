# ADR-0102: An approval a run asked is withdrawn when the run ends before it pauses on it

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** lattice [RFC-0011](../../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md)'s "withdrawn when its run is stopped", the follow-up [ADR-0101](0101-a-run-paused-on-an-enforcers-approval-names-it-and-is-answered-in-its-store.md) leaves

## Context

lattice's enforcer asks an approval, and stores it pending, as the call is made. The call then raises pydantic-ai's `ApprovalRequired`, and the run pauses once every call of its step has returned. Only then does `run_paused` name the approval, and the Runner follows it (ADR-0101).

A run can end in that window, before it pauses:

- it is stopped, by `stop_run`, by the Runner's `aclose`, or because its process lost its thread's claim;
- another call of the same step fails, and the run with it.

The approval stays pending in the store. portalr's approvals list shows it, and its answerers are asked for a call that no run will make. An answer to it lets nothing through, since only a call that presents its id goes ahead on it, but it waits for someone to answer, or until its deadline.

RFC-0011 says an approval is withdrawn when its run is stopped. A paused run is never stopped in artifactr (`stop_run` stops a run running in a process), and once it pauses, the Runner follows its approvals until the store settles them. So the window above is the one in which an approval is left behind.

## Decision

- **A run segment notes each approval it asks.** `Session.asked` holds the id of each approval the enforcer asked for the segment's calls. The capability's `wrap_tool_execute` adds it as the bridge's `ApprovalRequired` passes, read from its metadata under lattice-core's `APPROVAL` key. A tool's own `ApprovalRequired` names no approval, and nothing is noted.
- **A segment stopped or failed withdraws them.** Once the agent's run raises, cancelled or failed, the Runner withdraws each approval in `Session.asked` from its store before the error goes on. The thread has recorded the run's end by then. The reason is `its run was stopped` or `its run failed`, which the store records and portalr shows.
- **One settled already is left as it is.** If someone answered it meanwhile, or it expired, the store refuses the withdrawal (`NotPending`), and the answer stands. An approval the store doesn't know is left too.
- **One the store fails to withdraw is logged** and expires at its deadline. The run ends all the same.
- **A Runner given no store withdraws nothing,** as it answers nothing (ADR-0101). The application's enforcer may still ask its own store, whose approvals then expire at their deadline.
- A segment that pauses or completes withdraws nothing. One that pauses waits on its approvals, which the Runner follows; one that completes asked none, since an approval asked always pauses its run.

## Options considered

### Option A: Note them in the run segment's session (chosen)

**Pros:** artifactr alone carries it out, through the store's own `withdraw`, at the moment the run ends. It needs nothing new of lattice-core or of grantr's store.
**Cons:** what is noted lives in the process. A process that dies in the window can't withdraw its approvals, which expire at their deadline.

### Option B: Ask the store for the run's pending approvals

The store keeps who asked each approval, a `RunCaller` with the run's id. The Runner could ask the store for those still pending when a run ends, and when it records a dead process's run as abandoned.

**Pros:** it covers a run a dead process left, too.
**Cons:** `Approvals` has no read by caller. Adding one changes lattice-core's contract, which every store implements, and grantr's store and its index with it, for a window of a step's length.

### Option C: Record each asked approval in the log

**Pros:** a dead process's run could be swept from the log.
**Cons:** a new event, or a new field on `tool_returned`, changes artifactr's protocol and its schema, for the same narrow window.

## Consequences

- Easier: portalr's approvals list shows only approvals a run waits on, or ones its answerers can still act on.
- Easier: an approval's record in grantr says why it closed, `its run was stopped` or `its run failed`.
- Harder: an approval that a dead process's run asked, in the window before it paused, stays pending until its deadline. Option B can close that, once the store reads by caller.
- To revisit: Option B, if grantr's store gains a read by caller for another reason.
