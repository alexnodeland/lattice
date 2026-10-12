# ADR-0064: Asking for a thread's next turn

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

relayr starts a turn with `Runner.send(workspace, thread_id, content, message_id=...)`, with a message id derived from the rule's run, so a retried run sends the same id ([relayr ADR-0019](../../relayr/adr/0019-runs-act-once-through-derived-ids-and-keyed-edits.md)). `send` commits the message, then asks for the thread's next turn ([ADR-0055](0055-turns-from-the-log.md)). If the process stops between the two, the message is in the log and nothing asked for a turn. A retry gets `InvalidState` for the used id ([ADR-0045](0045-a-message-id-is-used-once.md)), and does nothing, so the message waits until something else asks for the thread ([lattice #80](https://github.com/alexnodeland/lattice/issues/80)).

## Decision

- **`Runner.ask(workspace, thread_id)`** asks for the thread's next turn, for whatever its log has that no turn has taken, up to the log's head. It returns the run it started, or `None`, as `resume` does. With nothing untaken, it does nothing.
- **It is asked as `send` is:** `authorize` hears `artifactr:record` in the thread, from the agent acting for the handle's actor (ADR-0057), so a caller who may not start a turn by sending may not start one by asking.
- **`send` is unchanged.** A caller that finds its message id used asks for the turn itself.
- **`resume` keeps its own checks.** It reads the run (`artifactr:read_runs`) and asks nothing more: the turn it resumes is the paused run's, whose answers were checked as they were committed, and the turn checks its agent as it starts. `ask` names no run, so it asks what `send` asks before it starts one.

## Options considered

| Option | For | Against |
|---|---|---|
| **A public ask (chosen)** | One small method beside `resume`, over the same ask and claim | The caller asks after an `InvalidState`, a second call |
| `send` idempotent by message id | One call | `send` must read back who posted the id, in which thread, and whether a turn took it, on every retry; a used id stops meaning "nothing was done" |

## Consequences

- Easier: relayr closes ADR-0019's window by asking after a used id.
- Harder: a caller that retries `send` must know to ask after a used id; the agent guide says so.
