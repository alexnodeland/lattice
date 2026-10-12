# ADR-0062: Restricted items left out of every read

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Amends [ADR-0056](0056-access-asked-in-every-workspace-method.md): a hidden item is missing, where a refused one was forbidden.

## Context

Lattice RFC-0001 lets an application restrict a thread or artifact to some of a workspace's members, and gives artifactr a second hook, `hidden`, that returns what one actor may not see. Its phase 5 asks that every read path leave those items out: listings, single reads, the log, the WebSocket's replay and live frames, MCP, and the agent's tools in a turn for another user. ADR-0056 already sends every surface through a `Workspace` method, so the question is where in those methods to filter, and what a hidden item looks like to whoever can't see it.

## Decision

- **`Workspaces(hidden=, hidden_refresh=)` holds the hook,** beside `authorize`. It answers with `artifactr.core.Visibility`, or any object with its `threads` and `artifacts` sets (the `Hides` protocol), so an access library's own answer fits without importing artifactr. Without a hook, nothing is hidden.
- **A hidden item is missing.** A method whose access names a hidden thread or artifact raises `NotFound` before `authorize` is asked, as for one that doesn't exist, so ids can't be probed by telling 403 from 404. That covers single reads, commands and claims. `run` and `proposal`, whose access names no item, are missing when their thread or artifact is hidden; answering a proposal, answering a paused run, and feedback on a turn or one of its messages are asked again of the artifact or thread they act on, and are refused, or missing as the proposal or run itself, naming no id the caller didn't give. A focus may name no hidden artifact, and keeps the hidden ones it had, which its setter can't have chosen to drop. A hidden thread's runs and history are empty, as a missing thread's are. `tests/workspace/test_hidden.py` calls each of these with a hidden id and a made-up one, and checks they answer alike.
- **Listings leave hidden items out:** artifacts, threads, proposals and runs. A thread's focus leaves out hidden artifacts.
- **The log drops what is about a hidden item.** An artifact or proposal event committed from a hidden thread is kept, without its thread and run, so a visible artifact's history stays whole. Nothing kept names a hidden thread: a hidden thread's agent, as an envelope's actor, a proposal's author or an artifact's last editor, is named with an empty thread and no run; an envelope kept from a hidden thread has no `traceparent`, and a revision its agent made no `trace_id`.
- **A page of the log is full whatever was hidden:** `read` with `limit` or `last` reads on from storage until the page is full or the window ends, so a short page still means the end. The `Storage` port doesn't change.
- **A handle asks `hidden` at most once every `hidden_refresh`,** 30 seconds by default, so a request asks it once and an open subscription asks again as it goes. A run the WebSocket forwards live stops once its thread is hidden. The WebSocket replays the log a page at a time up to the head, then follows it, so its replay ends at the head even when the last envelopes before it are hidden.
- **An MCP subscription reads each artifact it names,** so one hidden, or that doesn't exist, is refused as a read of it is.
- **The agent reads as its turn's actor,** whose `on_behalf_of` the application's hook looks through, so a turn for one user can't surface what that user may not see.

## Options considered

| Option | For | Against |
|---|---|---|
| **Filter in the `Workspace` methods (chosen)** | Every surface goes through them already; one place to test | Each read asks the hook once more |
| Filter in each surface | Each surface sees exactly what it sends | Four places to keep in step, and the agent's tools would be a fifth |
| Filter in storage, with the hidden sets as a parameter | Pages filled in one query | A change to the `Storage` port and both adapters, for sets that are small |
| A hidden item is forbidden | Nothing to add to the check | 403 for a hidden item and 404 for a missing one tell them apart |

## Consequences

- Easier: a surface added later inherits the filter, and `tests/workspace/test_hidden.py` lists every `Workspace` method with what it hides, as the permission matrix lists what each asks.
- Harder: an open stream learns of a new restriction up to `hidden_refresh` later; commands are refused at once, since each asks.
- Harder: a client subscribed over MCP to an artifact before it was restricted is still told when it changes, though reading it is `NotFound`; a new subscription asks, as a read does.
- Harder: gaps in the log's `seq`, and `head_seq`, tell a reader that something it can't see happened, though never what.
- Harder: creating an artifact or thread with a restricted id answers `NotFound`, where an id in use answers a conflict; ids are random, so this tells nothing that can be aimed.
