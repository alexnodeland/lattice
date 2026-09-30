# ADR-0055: Turns from the log

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

## Context

[ADR-0020](0020-running-agents-in-threads.md) gave a message one meaning in a thread:

- In an idle thread, it starts a run.
- In a busy thread, it steers the run, whose watcher delivers it.
- In a paused thread, it is the reply.

"Busy" meant that the thread's claim was held. But a run holds its claim longer than it takes messages:

1. pydantic-ai closes the run's queue when the agent's run is over.
2. The capability stops its watcher and records the run's end.
3. Only then is the claim released.

ADR-0020's amendment relies on that order to tell an abandoned run from a live one. A message sent between 1 and 3 found the thread claimed, so it started no run, and no watcher delivered it. It was recorded and never answered ([#29](https://github.com/alexnodeland/lattice/issues/29)). docplan's scripted session posts its next message as soon as it sees `run_ended`, and it hung CI in that window. On SQL the window is wider still, since the watcher polls.

An answer sent as a run paused went wrong differently. A resume claimed the thread with the run's id as the holder. The pausing segment still held the claim under that id, so the claim was renewed, not refused. The resumed run started while the pausing one finished. The pausing segment's release then deleted the lease under it, and the `Runner` lost its handle.

A first fix carried out what the ending run missed, from the run's own, in-memory position, after it released the thread. Review found that this was not enough:

- A run that failed before its watcher started read the thread from its first message. A failure that persisted made turns without end.
- A second reply in the pausing window fell below the resumed run's watch.
- A send that stalled between its commit and its claim, or whose turn failed fast, had its message carried out twice.
- A message committed directly, without the runner, started a turn if it landed in the window, and none otherwise. [ADR-0051](0051-notices.md)'s context says such a message starts no turn.
- A sender that took the thread first skipped what the ending run had missed.

## Decision

The log decides what each turn carries out. A thread's messages are taken in the log's order, each by exactly one turn: as a run's prompt, as a paused run's reply, or through the watcher of the run that holds the thread.

- **Each thread keeps two positions**, in the storage's named cursors ([ADR-0046](0046-telemetry-that-composes-across-libraries.md)): `artifactr.runner/{thread_id}/asked` and `artifactr.runner/{thread_id}/taken`. Both only move forward.
  - `send`, `answer` and `resume` save **asked**: the seq of the message or answer they commit (for `resume`, the log's head). They save it *before* they try to claim the thread, so a holder that refuses them sees it when it releases the thread.
  - The claim's holder saves **taken**. When it starts a turn, it saves it through the message the turn starts with; for a run that resumes by its answers, through what it read. When the turn ends, it saves it through what the turn's watcher delivered, before the claim is released. So a message the watcher misses is left for the next turn.
  - A thread with no taken position of its own starts from the upgrade, or from what its agent was last told, whichever is later. The upgrade point is where the workspace's log stood when SQL migration 0005 ran, as a deploy does. The migration records it once per existing workspace, as the cursor `artifactr.runner/upgraded`. So:
    - Nothing from before the upgrade resurfaces: not old messages, not messages lost in the window, and not the prompts of runs that failed.
    - A message committed after the upgrade is the next turn's, even before any turn has started, and whichever process touches the thread first.
    - A brand-new thread starts from its beginning.
    - What the agent was last told covers a run without the runner, which saves history but no position.
- **Whoever holds the claim decides.** When more was asked than has been taken, the holder reads the log after the taken position and finds the messages others posted that no turn has taken. Then, holding the thread:
  - If the thread's run is paused with requests open, the oldest of those messages is the reply: it answers the questions, declines the approvals, and the run resumes.
  - If the paused run's requests are all answered, the run resumes.
  - Otherwise the oldest message starts a run, as its prompt.
  - The turn's watcher follows from that message, or from the taken position when a run resumes by its answers. So the later messages reach the same turn.
  - With no message to carry out, the holder counts what it read as taken, releases the thread, and looks again.
  - A claimant that finds the thread claimed does nothing more: the holder hands the thread over.
- **A run that releases its thread hands it over.** A task of its own claims the thread, as any claimant would, when more was asked than taken. The run's end does not wait for it: `RunHandle.wait` returns the run's result, and `stop` does not reach it. `Runner.drain` waits for the hand-overs in progress, and `aclose` cancels them. A closed runner hands nothing over. The thread's next claimant, in any process, carries it out.
- **Each claim has a holder of its own**, never the run's id, so a resume cannot renew the claim its pausing segment still holds.
- **The watcher stops before the run's end is recorded**, however the run ends, so the position it reached is exact. It stops quietly when pydantic-ai no longer takes messages.
- **A message committed directly asks for nothing.** It starts no turn, but the thread's next turn takes it: as its prompt if it is the oldest, or through its watcher.
- **A hand-over's turn links to where it came from**: the span in which the message or answer it carries out was committed ([ADR-0035](0035-a-turn-is-its-own-trace.md)). A turn that a command starts links to the command's span, as before.

What this guarantees: each message sent to a thread's agent is carried out once, in the log's order, whoever takes the thread and in whichever process. Every turn takes a message that no turn took before, or resumes a run by its answers. So a failure, however often it repeats, cannot multiply turns.

## Options considered

Where the positions live:

| Option | Protocol | A turn that fails before it starts | A run whose process dies |
|---|---|---|---|
| **The storage's named cursors (chosen)** | Unchanged. Storage already keeps cursors (SQL migration 0004) | Its start saved the position, before its task ran | Its start saved the position |
| A field on `run_ended` and `run_paused` | A new field in `schemas/artifactr.v1.json` and in the frames every client reads, to carry an internal handoff | Records no end, unless `run_started` carries a start position as well | Has no end of its own to read |

Where a thread from before this record starts:

| Option | Assessment |
|---|---|
| **The upgrade point that migration 0005 records for each workspace (chosen)** | Exact: a message committed after the deploy is new, whichever process touches the thread first. Nothing older resurfaces |
| The head as it stood at the thread's first touch, before that command's commit | A direct message committed after the deploy but before the first send would count as old |
| What its agent last saw | The messages lost to the bug and the prompts of failed runs would resurface, as the first turn's input |

What starts a turn:

| Option | A message committed directly | Depends on timing |
|---|---|---|
| **More asked than taken (chosen)** | Starts none; the next turn takes it | No |
| Any message not taken | Starts one if it lands as a run ends, none in an idle thread | Yes |

When an ending run hands its thread over:

| Option | Assessment |
|---|---|
| **In a task of its own, after the release (chosen)** | `wait` is the run's own; `stop` cannot cancel a hand-over by stopping a run that has ended |
| In the run's task, after the release | `wait` includes the hand-over, and `stop` on an ended run cancels it, dropping others' messages |

Closing the window at its source, by releasing the claim in the transaction that records the run's end, was also considered. It needs:

- a lease release inside both adapters' transactions;
- a capability that knows about claims (direct runs hold none);
- a renewal stopped before that release.

And it still misses the stretch between the agent's run ending and its end being recorded, and SQL's polling lag.

## Consequences

- Easier: the rule is one sentence, and it holds for the WebSocket, REST, MCP and every process alike.
- Easier: a client may post the moment it sees `run_ended`, or while a run pauses. Its message is carried out.
- `Sent.run`, and `Recorded.run_id` on the wire ([ADR-0048](0048-surfaces-over-the-runner.md)), name the turn a command started. That turn may take an older message first. They are `null` also when the thread's holder will hand the thread over to the turn that takes the message.
- **Behaviour change:** a message committed directly is the input of the thread's next turn. Before, only a turn already running was told of it; in an idle thread the agent never was.
- **Upgrading:** each existing thread starts from where its workspace stood at the upgrade, so the agent never suddenly answers old messages. Messages lost to the bug before the upgrade, and failed runs' prompts from before it, stay untaken. Recording the point at first touch would not do: a direct message committed after the deploy but before the first send would then count as old. A database made with `create_schema` has no upgrade point, and its threads start from their beginning, as brand-new ones do.
- A run that fails keeps what it took: its prompt or reply, and what its watcher delivered, are not given again. The messages it had not been given yet go to the next turn. `resume` cannot retry a resume that failed before it began, since its answers are taken; the thread's next message resumes the run.
- Cost: `send` and `answer` save one cursor and read two before they claim the thread. Every claimant reads the log after the taken position.
- Tests wait for hand-overs with `Runner.drain`, since the ended run no longer carries them.

## Action items

1. [x] The asked and taken positions, the claimant's plan, hand-overs, a holder per claim, `Runner.drain` and the watcher's order; with a test for each case, and across two processes on PostgreSQL.
