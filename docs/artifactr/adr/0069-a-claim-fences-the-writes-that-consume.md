# ADR-0069: A claim fences the writes that consume

**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Alex Nodeland

Amends [ADR-0055](0055-turns-from-the-log.md).

## Context

[ADR-0055](0055-turns-from-the-log.md) holds a thread with a claim, a lease in storage, and says a message is consumed once (I1) and one run is active in a thread (I3). Nothing in the write that consumes a message checked the claim, so both rested on timing: on the claim's holder finding it lost, through its renewal's timer, before another process took it.

TLC, checking the thread claim's spec ([`docs/artifactr/spec/`](../spec/README.md)) with claims that lapse while their holders live, found that timing is not enough ([lattice #249](https://github.com/alexnodeland/lattice/issues/249)):

1. Process A claims a thread and plans a run for its oldest message.
2. A's claim lapses in storage before A's run records `run_started`.
3. Process B claims the thread. No run is `running`, since A's has not started, so B abandons none, reads `taken` unchanged, and plans a run for the same message.
4. Both `run_started` writes commit. The message is a run's prompt twice, and two runs are active.

A claim lapses under a live holder two ways. A write in flight past the TTL is run to its end, since storage finishes each call. And SQL storage stamps a lease's expiry with the application's own clock, so a process whose clock runs ahead of A's sees A's claim expired while A's timer has not fired: A is not stalled at all, and is never cancelled. `Runner`'s `claim_ttl` already asks to exceed the clock skew between replicas; nothing held a deployment to it.

## Decision

- **The writes that consume a message under a claim are fenced by it:** `run_started`, which consumes a run's prompt, and each answer a reply commits. Each is made only while the claim's holder has the thread's lease, checked in the write's own transaction.
- **The fence is the holder, not the time.** A lease that has expired, and that no one else took, still fences its holder's write: whoever takes it next abandons a run that started under it, as ADR-0055 does for a run its process left. So the fence needs no clock, and skew between processes cannot break it.
- **Storage's `Transaction` gains `holds_lease(key, holder)`.** It answers whether the holder has the lease, and keeps it so until the transaction ends: SQL storage locks the lease's row (`SELECT ... FOR UPDATE`), so `acquire_lease` for another holder waits for the transaction; in-memory storage's `acquire_lease` takes the workspace's lock, as its transactions do.
- **`Workspace.commit` and `Workspace.record` take `claim=(thread_id, holder)`,** beside `cursor=`. A write whose holder no longer has the thread is refused with `ThreadBusy`, and nothing is written.
- **The Runner names its claim to the run** through the session's `Delivered`, as it names the `taken` cursor. A run whose start is refused fails before it starts, consumes nothing, and hands over as ADR-0055's I4 says. A reply refused in `_plan` ends the claimant's round, as `ThreadBusy` at the claim does: the claimant that took the thread plans its turn.
- **The run's end is not fenced.** A run's end is refused by core once the run is abandoned, which the next claimant does before it plans, so an end recorded under a lapsed claim consumes nothing another turn took. Fencing it too would refuse a completed run's end, with its history, for no gain.

## Options considered

### Option A: The claim's holder, checked in the consuming write's transaction (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one storage method, one parameter, a field on `Delivered` |
| Clocks | None: the holder is compared, not the expiry |
| Storage protocol | `Transaction.holds_lease`: a storage written outside artifactr implements it |

**Pros:** the invariant is one sentence and holds whatever the timing; the same shape as reflexr's epoch fence ([lattice #247](https://github.com/alexnodeland/lattice/pull/247)), a fence checked in the transaction that writes.
**Cons:** a consuming write locks the lease's row, and a claim renewal in flight waits for it.

### Option B: Compare `taken` with what the plan read

`run_started` would save its cursor only if `taken` still stood where the plan read it.

**Pros:** no change to storage's protocol.
**Cons:** `taken` is read through the upgrade point and what the agent was last told, and a reply moves it within a plan, so the value the plan read is not the stored one; the compare would need to know which. And it fences only what moves `taken`: an answer is refused by core per request, not per message, so two replies could still take one message to two requests.

### Option C: Lease time from the database's clock

`acquire_lease` would stamp expiries with the database's `now()`, so processes agree on when a claim lapses.

**Pros:** removes the skew.
**Cons:** leaves the write in flight past the TTL, the other way a claim lapses under a live holder; the in-memory storage has no database clock; and it is still timing.

### Option D: Core refuses `run_started` while another run is active

**Cons:** fences I3 and not I1. Once the first run ends, a second, planned under a lapsed claim before it started, starts with the same prompt.

### Option E: Name a second exception in ADR-0055

**Cons:** a prompt recorded twice is two replies to one message, which a person sees; ADR-0055's one exception, steering given again to the model, is not visible.

## Trade-off analysis

Options C and D narrow the window; only a fence closes it. Option B fences the cursor, and has to reconstruct what the plan read; option A fences the claim itself, whose holder is a value the Runner already makes for each claim. The cost of A is a method in storage's `Transaction`, which ADR-0055 already extended for `save_cursor`, and a row lock held for one write.

## Consequences

- Easier: I1 and I3 hold under a stalled write and under clock skew, and `claim_ttl` exceeding the skew between replicas is no longer what holds them; it still sets how soon a dead process's run is abandoned.
- Easier: the spec checks it. `ThreadClaimLapse.cfg` runs in CI with `I1_ConsumedAtMostOnce` and `I3_OneActiveRun`; `RunStart` and `Reply` require the claim in storage to be their own, and `StartFenced` and `ReplyFenced` are the refusals. TLC finds a run's start without the fence violates `I3_OneActiveRun` in 16 states.
- Harder: storage's `Transaction` protocol grows `holds_lease`. Only artifactr's two storages implement it in the packages.
- A run whose start is refused by the fence is a failed turn, in the turn's span and metrics, and its `RunHandle.wait` raises `ThreadBusy`. It consumed nothing.
- ADR-0055's one exception stands: steering a stalled run was given, and could not record, may be given again by the thread's next holder.

## Action items

1. [x] `Transaction.holds_lease` in both storages; `claim=` on `Workspace.commit` and `Workspace.record`; the Runner fences `run_started` and the reply's answers ([lattice #249](https://github.com/alexnodeland/lattice/issues/249)).
2. [x] The spec's `RunStart` and `Reply` are fenced, and `ThreadClaimLapse.cfg` runs in CI.
