# ADR-0070: A runner looks again for what a dead holder was asked

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

Amends [ADR-0055](0055-turns-from-the-log.md).

## Context

[ADR-0055](0055-turns-from-the-log.md) leaves a thread's next turn to whoever holds its claim: a claimant that finds the thread claimed does nothing more, and the holder hands the thread over as it releases it (I3). A holder whose process dies never releases it. Its claim lapses in storage, but nothing looks at the thread then.

TLC, checking the thread claim's spec ([`docs/artifactr/spec/`](../spec/README.md)) with a crash and callers that ask again, found what that leaves ([lattice #252](https://github.com/alexnodeland/lattice/issues/252)):

1. A message is sent and asked for. Its claimant claims the thread, plans its turn, and its process dies.
2. A message sent meanwhile, or a caller that asks again, finds the thread claimed, and returns. `Sent.run` is `None`, which its docstring says means the holder will hand the thread over.
3. The claim lapses, and the process starts again. Nothing reads the thread's `asked` beyond its `taken`, so both messages wait for the thread's next command, however long that is.

A process that dies alone, with no other process to refuse, strands what it was asked the same way: a message it was steering its run with, or one it asked for and had not claimed.

## Decision

- **A claimant refused as busy looks again once the claim could have lapsed.** `_take`, on `ThreadBusy`, schedules a look at the thread a `claim_ttl` on. By then, a claim that refused it has lapsed if its holder was dead at the refusal, and the look takes it. Otherwise the look is refused, as by a live holder, one that died later, or one whose replica's `claim_ttl` is longer, and waits again, until what was asked is taken. A thread has one such wait at a time in a process. A look that fails, as on a storage error, is logged and not armed again: what was asked waits for the thread's next command, or for `recover`.
- **`Runner.recover(workspace)` sweeps a workspace as an application starts.** It takes each thread's turn that was asked for and not taken, as the Runner, and returns the runs it started. It asks nothing of the handle's actor, as a hand-over asks nothing, and it is idempotent, so any replica may call it, at start or on a schedule. A thread whose dead holder's claim has not lapsed yet is refused, and looked at again as above. A thread whose turn fails to start is logged, and the sweep goes on. The Runner holds no list of workspaces, so the application calls it for each of its own.
- **A look is the Runner's own work, as a hand-over is.** It acts as `SystemActor(name="runner")`, in a context of its own, and a failure is logged, never raised. `Runner.drain` does not wait for it, since a live holder can keep it waiting for as long as its run lasts; `Runner.aclose` cancels it, and a closed runner schedules none.
- **ADR-0069's fence is what makes taking a lapsed claim safe.** A holder whose claim lapsed while it lived, as across a stall, may be looked past: its `run_started`, and its reply's answers, are refused by their claim, so the look's turn is the only one that consumes.

## Options considered

### Option A: Look again after a refusal, and sweep at start (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: a timer per refused thread, and a public method over `_take` |
| Cost | While a holder in any process runs with a message refused, a lease attempt and three cursor reads per `claim_ttl`; at start, the same reads for every thread of every workspace, one after another, before the application is ready |
| What it covers | A holder that dies while another process waits on it, and a process that dies alone |

**Pros:** each half is `_take` again, so the plan, the fence and the hand-over are unchanged; the spec checks that nothing asked is stranded with a crash.
**Cons:** a message waits up to two `claim_ttl`s from its holder's death; the application calls `recover` itself, and its start is slower by a read of every thread.

### Option B: Document it

ADR-0055 would say that a crash leaves what was asked to the thread's next command, and `Sent.run`'s docstring would stop promising a hand-over.

**Pros:** no code.
**Cons:** a message can wait for good in a thread no one writes to again, and a caller has no sign of it: `Sent.run` is `None` for a busy live thread too.

### Option C: Look again after a refusal only

**Pros:** no public method.
**Cons:** a process that dies alone leaves its asks with no claimant refused, so no one looks. TLC finds `AskedIsTaken` violated in 12 states.

### Option D: Sweep at start only

**Pros:** no timers.
**Cons:** what a live process was refused waits until some process starts again, which a deployment that keeps its other replicas running may never do. TLC finds `AskedIsTaken` violated in 17 states.

### Option E: Watch the lease, and look when it is released or lapses

**Pros:** a look would come as soon as the claim is free.
**Cons:** storage's protocol has no way to wait on a lease, and polling it is option A with a shorter period.

## Trade-off analysis

Option B is what ADR-0055 designed, but a message that waits for good is a turn a person never gets, with nothing to show it. Options C and D each close one of the two ways a death strands an ask; only together do they close both, which TLC confirms by the trace each leaves. A timer of a `claim_ttl` is the longest a dead claim can stand after a refusal it made: looking sooner trades refusals for latency, and looking later only delays the turn.

## Consequences

- Easier: `Sent.run`'s promise holds. A message refused by a busy thread is taken by its holder's hand-over, or, if the holder died, by this process once the claim lapses.
- Easier: the spec checks it. `Refused` marks the process to look again, and `LookAgain` reads the cursors once the claim can be taken, in the background of whatever else the process does; `Restart` sweeps the thread. `ThreadClaimRecovery.cfg` runs in CI with a crash, checking `AskedIsTaken` and `SentIsTaken`, in under a minute; with a fault as well it holds too, but takes about six minutes and 5.6 million states, too long for a pull request, so `ThreadClaimLive.cfg` keeps the fault and no crash.
- Harder: an application calls `Runner.recover` for its workspaces as it starts. docplan does, in its lifespan. `AskedIsTaken` under a crash rests on it: a process that died alone, and never starts again, leaves its asks until some replica calls `recover`, or the thread's next command.
- A look that runs while a live holder steers its run is refused every `claim_ttl` until the run ends, since steering is taken only with the run's end. That holds for a holder in this process too, whose hand-over the look does not need: telling the two apart would need the claim's holder from storage, and the look costs one lease attempt and three reads per `claim_ttl`.
- What a dead run was given is given again by the turn that takes its thread: [ADR-0055](0055-turns-from-the-log.md)'s amendment of 2026-10-17 accepts it ([lattice #257](https://github.com/alexnodeland/lattice/issues/257)).

## Action items

1. [x] `_take` looks again after `ThreadBusy`; `Runner.recover`; `aclose` cancels the looks; docplan recovers its workspaces as it starts ([lattice #252](https://github.com/alexnodeland/lattice/issues/252)).
2. [x] The spec's `Refused` arms a look and `LookAgain` takes it; `Restart` sweeps; `ThreadClaimRecovery.cfg` runs in CI.
