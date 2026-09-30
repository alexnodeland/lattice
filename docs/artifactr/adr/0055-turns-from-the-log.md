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

A second review, of the design below as first written, found more:

- `resume` asked up to the log's head, which may be another thread's event, while the plan read only the thread. More was always asked than taken, so it claimed without end.
- The start of a turn saved its position before the run's task existed. A cancelled send, or a runner closed as it handed a thread over, lost the message.
- A resume by answers counted as taken the messages its watcher had yet to deliver.
- A run whose process died after recording its end, but before recording its position, had its steering given again.

A third review found the pattern behind every loss and duplicate: a message was consumed by one log write, and its position was saved by another. It named three more:

- A reply racing an answer was refused, and stranded the thread.
- A message left to a holder that failed or was stopped before it started was never handed over.
- With no position of its own, a thread's first run lost what it missed.

## Decision

The log decides what each turn carries out, and each message is consumed in the transaction of the write that consumes it.

### Invariants

- **I1.** Every message in a thread's log, notices aside, is consumed exactly once. It is a run's prompt, a paused run's reply, or a message delivered to the run that holds the thread.
- **I2.** A message's consumption is recorded in the same transaction as the log write that consumes it:
  - the start of the run it prompts;
  - the answer it replies with;
  - the end of the run it was delivered to.
- **I3.** A claim is never held without a task to release it. A claim is never released while more was asked than taken, unless a hand-over reads what was asked *after* the release, so it sees any command it refused. After a run ends, or a claimant or a run is cancelled or stopped, the hand-over takes whatever was asked and not taken. After a claimant or a run fails having consumed nothing, it takes only what was asked after the claimant's read.
- **I4.** A turn that fails or is stopped before it starts consumes nothing.
  - If it was cancelled or stopped, it hands over whatever was asked and not taken, including a command that asked before its holder read, and its own input.
  - If it failed, it hands over only what was asked after its holder read. A command that asked before that read waits for the thread's next command, which consumes it first. So a failure that persists makes one turn per command, and never spins.
- **I5.** A message committed directly, without the runner, starts no turn, and the thread's next turn consumes it. A notice is never a prompt or a reply.
- **I6.** A message is a message. In a paused thread, the oldest message not yet consumed is the reply, however it was committed and whoever posted it. Anything that should not answer is posted as a notice ([ADR-0051](0051-notices.md)).
- **I7.** A thread from before this record consumes nothing from before the upgrade point, which migration 0005 records again after a downgrade and a second upgrade.
- **The one exception.** A claim can lapse while its holder lives, as when a process or its storage stalls past `claim_ttl`. Then a message that the stalled run was delivered, and could not record, may be consumed again by the thread's next holder.

### How

- **Each thread keeps two positions**, as rows in the storage's named cursors: the table [ADR-0046](0046-telemetry-that-composes-across-libraries.md) gave the feedback mirror. They are `artifactr.runner/{thread_id}/asked` and `artifactr.runner/{thread_id}/taken`. Both only move forward. They are durable internal state: renaming them sends every thread back to the start point below.
  - **asked** is saved before the thread is claimed, so a holder that refuses a claim sees it when it releases the thread. `send` saves its message's seq; `answer` and `resume` save the log's head.
  - **taken** moves only inside a transaction that consumes. The storage protocol's `Transaction` gains a `save_cursor`, buffered like its history, and `Workspace.commit` and `Workspace.record` take a `cursor=` to save with the write. The capability saves taken with the run's start, through the run's input: its prompt, or its reply, and what came before its watcher's start. It saves taken again with the run's end, whether completed, paused, failed or stopped, through what its watcher delivered. A reply saves it with the answer it commits.
  - A thread's taken position is never before the upgrade point, so what an older release carried out between a downgrade and a second upgrade is not carried out again. A thread with no taken position of its own starts from the later of two points: the upgrade, or what its agent was last told. The upgrade point is where the workspace's log stood when SQL migration 0005 ran, as a deploy does. The migration records it once per existing workspace, as the cursor `artifactr.runner/upgraded`. A brand-new thread starts from its beginning. What the agent was last told covers a run without the runner, which saves history but no position.
- **Whoever holds the claim decides.** When more was asked than taken, the holder reads the log's head. It then reads the thread's log after the taken position, which covers every event of the thread up to that head. It finds there the messages others posted that were not consumed. Holding the thread:
  - If the thread's run is paused with requests open, the oldest of those messages is the reply. It answers the questions and declines the approvals, and the run resumes. A request refused because an answer committed without the claim came first is left as answered. If the message answered nothing, the holder plans again.
  - If the paused run's requests are all answered, the run resumes. Those messages are its prompt beside the answers, so they reach the model with its first request.
  - Otherwise the oldest message starts a run, as its prompt.
  - The turn's watcher follows from there, so later messages reach the same turn.
  - With no message to consume, the holder counts what it read, up to the head, as taken. It releases the thread and looks again.
  - A claimant that finds the thread claimed does nothing more: the holder hands the thread over.
- **A run hands its thread over as it releases it**, in a task of its own. So does a claimant that is cancelled, or fails, before it becomes a run, as when a client that sent a command disconnects. The hand-over reads what was asked, and what was taken, after the release, and it proceeds in three cases:
  - the claimant consumed something;
  - it was cancelled or stopped;
  - more was asked since it read.

  A failure that consumed nothing thus hands over only a new ask, so it makes one turn per command. A cancelled or stopped claimant hands over everything not taken, since a command it refused may have asked before it read. Neither can spin: only `aclose` cancels a hand-over, and it closes the runner first.
  - The run's end does not wait for the hand-over: `RunHandle.wait` returns the run's result, and `stop` does not reach it.
  - `Runner.drain` waits until no hand-over is pending, and `aclose` cancels them instead.
  - A closed runner hands nothing over, and starts no run once `aclose` has begun. The thread's next claimant, in any process, carries it out.
- **A claim is always held by a task.** The run's session is set up while the claimant still holds the claim, so a failure there releases it. The run's task starts eagerly, holding the claim before anything can cancel it.
- **Each claim has a holder of its own**, never the run's id, so a resume cannot renew the claim its pausing segment still holds.
- **The watcher stops before the run's end is recorded**, however the run ends. It stops quietly when pydantic-ai no longer takes messages.
- **A hand-over's turn links to where it came from**: the span in which the message or answer it carries out was committed ([ADR-0035](0035-a-turn-is-its-own-trace.md)). A turn that a command starts links to the command's span, as before.

## Options considered

When a message's consumption is recorded:

| Option | A turn cancelled or failed before it starts | A process that dies between writes |
|---|---|---|
| **In the transaction of the write that consumes it (chosen)** | Consumes nothing | Consumes exactly what its last write recorded |
| As the run ends, in a write of its own | Consumes nothing | Its input is consumed again, and people may see a second reply |
| As the run starts, before its task runs | Loses its input: a cancelled send, or a runner closed as it hands over | Its input is lost |

The chosen option costs a `save_cursor` in the storage protocol's `Transaction`, about ten lines in each adapter, and a `cursor=` on `Workspace.commit` and `Workspace.record`.

Where the positions live:

| Option | Protocol | A run whose process dies |
|---|---|---|
| **The storage's named cursors (chosen)** | Unchanged. Storage already keeps cursors (SQL migration 0004) | Its position is what its last write recorded |
| A field on `run_started`, `run_paused` and `run_ended` | A new field in `schemas/artifactr.v1.json` and in the frames every client reads, to carry an internal handoff | The same, read back from the log |

Where a thread from before this record starts:

| Option | Assessment |
|---|---|
| **The upgrade point that migration 0005 records for each workspace (chosen)** | Exact: a message committed after the deploy is new, whichever process touches the thread first. Nothing older resurfaces |
| The head as it stood at the thread's first touch, before that command's commit | A direct message committed after the deploy but before the first send would count as old |
| What its agent last saw | The messages lost to the bug and the prompts of failed runs would resurface, as the first turn's input |

What starts a turn:

| Option | A message committed directly | Depends on timing |
|---|---|---|
| **More asked than taken (chosen)** | Starts none; the next turn consumes it | No |
| Any message not consumed | Starts one if it lands as a run ends, none in an idle thread | Yes |

When an ending run hands its thread over:

| Option | Assessment |
|---|---|
| **In a task of its own, after the release, reading what was asked then (chosen)** | `wait` is the run's own, `stop` cannot cancel a hand-over by stopping a run that has ended, and a command refused while the run held the thread is seen |
| In the run's task, after the release | `wait` includes the hand-over, and `stop` on an ended run cancels it, dropping others' messages |
| Deciding before the release | A command that asks, then finds the thread claimed, between that read and the release is stranded |

Closing the window at its source, by releasing the claim in the transaction that records the run's end, was also considered. It needs:

- a lease release inside both adapters' transactions;
- a capability that knows about claims (direct runs hold none);
- a renewal stopped before that release.

And it still misses the stretch between the agent's run ending and its end being recorded, and SQL's polling lag.

## Consequences

- Easier: the rule is one sentence, and it holds for the WebSocket, REST, MCP and every process alike.
- Easier: a client may post the moment it sees `run_ended`, or while a run pauses. Its message is consumed.
- `Sent.run`, and `Recorded.run_id` on the wire ([ADR-0048](0048-surfaces-over-the-runner.md)), name the turn a command started. That turn may consume an older message first, however that message was committed. They are `null` also when the thread's holder will hand the thread over to the turn that consumes the message.
- **Behaviour change:** a message committed directly is the input of the thread's next turn, and in a paused thread it is the reply. Before, only a turn already running was told of it; in an idle thread the agent never was. Post a notice for what should not reach the agent as a message.
- **Upgrading:** each existing thread starts from where its workspace stood at the upgrade, so the agent never suddenly answers old messages. Messages lost to the bug before the upgrade, and failed runs' prompts from before it, stay unconsumed. Recording the point at first touch would not do: a direct message committed after the deploy but before the first send would then count as old. A database made with `create_schema` has no upgrade point, and its threads start from their beginning, as brand-new ones do.
- A turn that fails before it starts, such as when the application's `turn_context` raises, consumes nothing. The thread's next command consumes its input first. A turn that fails or is stopped once it has started keeps what it consumed.
- The storage protocol changes: a storage written outside artifactr implements `Transaction.save_cursor`.
- Cost: `send` and `answer` save one cursor and read two before they claim the thread. Every claimant reads the log's head and the thread's log after the taken position.
- Tests wait for hand-overs with `Runner.drain`, since the ended run no longer carries them. Each invariant has a test that runs in memory and on PostgreSQL. The three reviews' probes are kept as regression tests.

## Action items

1. [x] The asked and taken positions, saved with the writes that consume, the claimant's plan, hand-overs, a holder per claim, `Runner.drain`, eager runs and the watcher's order; with a test for each invariant on both storages, and the reviews' probes.
