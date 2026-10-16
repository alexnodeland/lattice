# ADR-0066: An epoch fences each attempt

**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Alex Nodeland

## Context

[ADR-0041](0041-executing-runs.md) discards a stale attempt: its outcome is recorded only if the run is still `running` at the same attempt, compared as `(status, attempts)`. `Reaction.checkpoint` is fenced the same way, through `Workspace.checkpoint_run(attempt=)`, and the lease keeper stops an action only once the run is no longer `running`.

`attempts` is not a fence. A retry of a finished run sets it back to 0, so that the run gets a fresh retry budget: `fail()` hands `attempts` to the rule's `RetryPolicy` for its backoff and its `max_attempts`. After a cancel and a retry, the next attempt is attempt 1 again, and the pair cannot tell it from the first ([lattice #245](https://github.com/alexnodeland/lattice/issues/245)):

1. Executor A claims a run and starts attempt 1.
2. An operator cancels the run and retries it: it is `pending`, with `attempts == 0`.
3. A's lease lapses, as when a renewal fails and the keeper stops, and executor B starts attempt 1.
4. A's action ends. The run is `(running, 1)`, as A claimed it, and A records its outcome over B's attempt, which is discarded in turn when it ends.

## Decision

- **A run has an `epoch`:** how many attempts it has started, retries included. `start()` adds one to it, and nothing else changes it, so it only grows and no two attempts of a run share one. It defaults to 0.
- **`attempts` keeps its meaning.** It counts the attempts in the current retry budget, a retry of a finished run sets it back to 0, and the retry policy, `RunStarted.attempt`, `RunRetrying.attempt` and `RunDeadLettered.attempts` read it as before.
- **The fence is `Run.is_running(epoch)`:** the run is `running`, at that epoch. Since only `start()` makes a run `running`, and it gives each attempt a new epoch, the fence holds for one attempt at a time, and only until the run leaves `running`, whatever sequence of cancels, retries, skips and lapsed leases comes between.
- **Every write an attempt makes checks it,** in the transaction that makes the write:
  - the executor's completion, which records `run_succeeded`, `run_retrying` or `run_dead_lettered`
  - `Workspace.checkpoint_run(run_id, *, attempt, epoch, step, state)`, which `Reaction.checkpoint` calls with its run's attempt and epoch; the epoch is the fence, and the attempt names it on the span and in the error
- **The epoch is on the spans** as `reflexr.run.epoch`, beside `reflexr.attempt`, on `invoke_workflow` and `reflexr.checkpoint_run`.
- **A graph resumed from a checkpoint prefixes its restored node runs' ids with the epoch,** not the attempt number, which a retry repeats. A checkpoint saved with the earlier `a{attempt}:` ids still resumes: they are nested under the new prefix, as `e1:a1:…`.
- **The lease keeper checks it too.** An attempt whose run is running another attempt is stopped at its next renewal, as a cancelled one is, even if its executor took the lease back.
- **No column, and no migration.** A run is stored as the JSON of its model ([ADR-0030](0030-sql-storage.md)), so the epoch is a field of the body, and a run stored before it reads as epoch 0. Every transaction locks its workspace's row before it reads ([ADR-0030](0030-sql-storage.md)), so comparing the epoch and saving the run in one transaction is as safe as a conditional `UPDATE`.

## Options considered

### Option A: An epoch beside `attempts` (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: a field, one line in `start()`, and one predicate in three places |
| Retry budget | Unchanged |
| Storage | No column, no migration |
| Public API | `Run.epoch` and `Run.is_running`; `checkpoint_run` takes `epoch=` beside `attempt=` |

**Pros:** the fence and the budget are separate facts, each with one job; the invariant is one sentence.
**Cons:** two counters on a run, which a reader must tell apart.

### Option B: Monotone `attempts`

A retry would keep `attempts`, and `(status, attempts)` would become a true fence.

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Retry budget | Needs a second field, the attempts at the last retry, for `fail()` to subtract |
| Events | `RunStarted.attempt`, `RunRetrying.attempt` and `RunDeadLettered.attempts` would count across retries, and the prompt's "This is attempt N" with them |

**Pros:** `checkpoint_run` keeps its parameter.
**Cons:** as many fields as option A, with the budget's arithmetic spread over `fail()`, the events and every reader of `attempts`.

### Option C: A version bumped by every transition

A row version, as optimistic locking uses.

**Cons:** `checkpoint()` would bump it, so the executor's copy of the run from its claim would go stale after the attempt's first checkpoint, and the attempt would discard its own outcome. Fencing the attempt, not the row, is what is wanted.

### Option D: The epoch alone, without the status

**Cons:** a cancelled run keeps its epoch, so the attempt it was running would pass the fence, and `succeed()` would raise `InvalidState`.

### Option E: The fence in the SQL `UPDATE`'s `WHERE`

**Pros:** the database itself refuses a stale write, whatever the code around it does.
**Cons:** nothing to add: the transaction already holds the workspace's lock when it compares the run, and the in-memory storage, which has no `WHERE`, would need the comparison in Python anyway.

## Trade-off analysis

The bug is that one counter served two purposes: a budget that must start over, and an identity that must never repeat. Option B keeps one counter for identity and derives the budget, which touches every reader of `attempts`; option A keeps the budget where it is and adds the identity, which touches only the three places that fence an attempt. Options C and D fence the wrong thing, and E fences in a place that is already serialised.

## Consequences

- Easier: no write of a stale attempt, an outcome or a checkpoint, lands, whatever happened to the run since it started. The run lifecycle's state machine test holds the pure part for random sequences of starts, completions, cancels, retries and skips: the epoch's bookkeeping, and that `is_running` passes only the current attempt. Example tests, on every storage, hold the executor's completion, its lease keeper and `checkpoint_run` to it.
- Easier: an attempt that lost its run to a newer attempt stops its action within a third of the lease's time to live, rather than running to its end.
- Harder: `Workspace.checkpoint_run` requires `epoch=` beside `attempt=`. Only `Reaction.checkpoint` calls it in the packages; reflexr has no release yet, so nothing published breaks.
- Harder: reactors from before and after this change must never run side by side, and rolling back is unsafe once the new code has saved runs. `Run` forbids unknown fields, and every body the new code saves carries `epoch`, so an older reactor refuses every run saved after the upgrade: rolled back, it breaks on those workspaces' runs. The model stays strict; loosening it would hide fields that matter, as this one does.
- The epoch counts starts since it existed: a run stored before it reads as 0, so its epoch undercounts its starts. That is harmless, as it is only a fence: a run `running` across the upgrade has epoch 0, its next start gives it 1, and an attempt from before the upgrade is fenced out once the run starts again.

## Action items

1. [x] `Run.epoch`, `Run.is_running`, and the fence in the executor's completion, its lease keeper and `checkpoint_run` ([lattice #245](https://github.com/alexnodeland/lattice/issues/245)).
2. [x] The run lifecycle's state machine completes stale attempts at random, and checks that `is_running` passes only the current one.
