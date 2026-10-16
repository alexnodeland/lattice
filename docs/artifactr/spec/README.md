# artifactr's thread claim, in TLA+

[`ThreadClaim.tla`](ThreadClaim.tla) is a model of how artifactr's `Runner` claims a thread and decides its turns ([ADR-0055](../adr/0055-turns-from-the-log.md)), and TLC checks it ([lattice ADR-0025](../../adr/0025-formal-specs-in-tla-and-lean.md)). It is the first of lattice's formal specs.

It models one thread and a few processes that send, ask, claim, plan, run and hand over, each with claims of its own. The claim is a lease that lapses, and a clock ticks it down as an action of its own. The `asked` and `taken` cursors are durable, and so are the log and the runs' status. Processes crash, fail and are cancelled at the code's awaits, and send at the same time.

The [action table](#the-actions-and-the-code-they-model) maps each step of the model to the code it stands for. It is an argument, made by reading the code: `scripts/check_spec.py` checks only that each action exists in the spec and each function it names exists in artifactr, not that the step does what the function does. Where that matters most, for the bugs below, a test runs the same behaviour against the code.

## What a run of TLC shows

TLC explores every behaviour within the bounds each configuration sets, and no other. A property that holds there is a small-scope claim, not a proof: many concurrency bugs already show with two processes and two messages, but nothing beyond the bounds is checked. A property TLC finds violated is a behaviour of the model, with the trace to show it; it is a behaviour of the code only as far as the model is the code, which is why each finding has a test.

| Configuration | Where it runs | Bounds | Checks |
|---|---|---|---|
| [`ThreadClaim.cfg`](ThreadClaim.cfg) | CI, when the spec or what it models changes (under a minute) | 2 processes, 2 messages or notices, a pause, a failure or cancellation, a crash | I1, I2, I3's one active run, I4, I5, I6 |
| [`ThreadClaimLive.cfg`](ThreadClaimLive.cfg) | CI, likewise (seconds) | 2 processes, 2 messages or notices, a pause; nothing fails, is cancelled or crashes | I3's claim and hand-over, and that what is asked or sent is taken |
| [`ThreadClaimDeep.cfg`](ThreadClaimDeep.cfg) | Nightly | 3 messages or notices, a TTL of 2 ticks, so a live holder renews its claim; no fault | Every property of the two above |
| [`ThreadClaimLapse.cfg`](ThreadClaimLapse.cfg) | Nightly | `ThreadClaimLive.cfg`'s, with claims that lapse while their holders live | I1's none skipped, I2, I6 |

No configuration in CI lets a claim lapse while its holder lives (`Stalls = FALSE`), and the live ones have no fault at all: that is where TLC finds the bugs below, and the configurations check what holds of the code today, so CI stays green. Each finding's issue says which property joins a configuration once it is fixed. At a TTL of one tick, the pull request's runs never renew a claim; Nightly's deep run does. CI runs TLC with `scripts/tlc`, which downloads `tla2tools.jar` at the version `scripts/tlc.sha256` pins, and checks its SHA-256 before it runs: 1.7.4, trusted on first download, which matched the SHA-1 the release notes publish; GitHub gives no digest for that release's assets.

## The properties

Each is named after the ADR-0055 invariant it checks, and tied to a test that holds the code to the same invariant. `scripts/check_spec.py` fails if the spec's header table, these names, the configurations, the tasks and the tests disagree.

| Property | ADR-0055 | Test | Kind | At the bounds |
|---|---|---|---|---|
| `I1_ConsumedAtMostOnce` | I1 | `test_i1_messages_sent_at_once_from_two_processes_are_each_consumed_once` | invariant | Holds; **violated when a claim lapses while its holder lives** ([#249](https://github.com/alexnodeland/lattice/issues/249)) |
| `I1_NoneSkipped` | I1 | `test_i1_a_message_sent_as_a_run_releases_its_thread_is_consumed_once` | invariant | Holds, with lapses too (`ThreadClaimLapse.cfg`) |
| `I1_GivenOnce` | I1, I2 | `test_i2_steering_is_consumed_with_the_runs_end` | invariant | Holds on behaviours with no crash and no lapse, the only ones it checks: a crash gives a dead run's steering to a model again ([#257](https://github.com/alexnodeland/lattice/issues/257)) |
| `I2_ConsumedWithItsWrite` | I2 | `test_i2_a_prompt_is_consumed_with_its_runs_start` | action property | Holds by the actions' construction |
| `I3_ClaimHasATask` | I3 | `test_i3_a_claim_is_released_when_its_run_cannot_be_set_up` | invariant | Holds without faults; **violated by a cancelled claim on SQL storage** ([#250](https://github.com/alexnodeland/lattice/issues/250)) |
| `I3_NoStrandedAsk` | I3 | `test_i3_a_command_that_asked_before_its_holder_read_is_handed_over` | invariant | Holds without faults; **violated by a cancellation after the ask** ([#251](https://github.com/alexnodeland/lattice/issues/251)) |
| `I3_OneActiveRun` | I3 | `test_i3_a_claim_that_lapses_as_its_run_starts_leaves_one_run` (strict `xfail`) | invariant | Holds; **violated when a claim lapses while its holder lives** ([#249](https://github.com/alexnodeland/lattice/issues/249)) |
| `I4_NothingTakenUnstarted` | I4 | `test_i4_a_turn_that_keeps_failing_before_it_starts_consumes_nothing` | action property | Holds by the actions' construction |
| `I5_DirectAsksNothing` | I5 | `test_i5_a_message_committed_directly_starts_no_turn_and_the_next_consumes_it` | action property | Holds by the actions' construction |
| `I6_OldestIsTheReply` | I6 | `test_i6_a_message_committed_directly_in_a_paused_thread_is_its_reply` | action property | Holds; checked only at Nightly's bounds, the first with two messages left while a run is paused |
| `AskedIsTaken` | I1, I3 | `test_i3_a_message_left_to_a_holder_that_never_starts_is_handed_over` | liveness | Holds without faults; **violated by a cancellation, a cancelled claim, or a crash** ([#250](https://github.com/alexnodeland/lattice/issues/250), [#251](https://github.com/alexnodeland/lattice/issues/251), [#252](https://github.com/alexnodeland/lattice/issues/252)) |
| `SentIsTaken` | I1, I5 | `test_i5_a_message_whose_ask_was_lost_is_consumed_once_its_thread_is_asked` | liveness | Holds without faults; **violated between a send's commit and its ask**, ADR-0045's known hole, unless the caller asks again (ADR-0064) |

I2, I4 and I5 say what the actions already say: each is a check on the spec, that an edit to it keeps them, and says nothing of the code beyond the action table. I2 is also weaker than ADR-0055's prose, as the code is: a plan that finds no message to carry out saves `taken` in a write of its own, which consumes nothing. The liveness properties assume nothing *fails* (a failure that consumed nothing hands over only a newer ask, by I4's design); cancellations and crashes may happen.

## How we know the checks can fail

A property that cannot fail checks nothing. Each change below, made to a copy of the spec, is caught by TLC:

| Change to the spec | Configuration | TLC |
|---|---|---|
| A run's start saves no `taken` | `ThreadClaim.cfg` | `I1_ConsumedAtMostOnce` violated |
| A hand-over never proceeds | `ThreadClaimLive.cfg` | `I3_NoStrandedAsk` violated |
| A run's end takes the whole log, delivered or not | `ThreadClaim.cfg` | `I1_NoneSkipped` violated |
| The reply is the newest message, not the oldest | `ThreadClaimDeep.cfg`, with `I6_OldestIsTheReply` alone | `I6_OldestIsTheReply` violated (at `ThreadClaim.cfg`'s bounds it holds, which is why I6 is checked nightly) |

And the behaviours the properties are checked over are reached. Each witness in the spec claims something never happens, and TLC finds it does, at `ThreadClaim.cfg`'s bounds, in the number of steps shown:

| Witness | Reached in |
|---|---|
| `NeverPaused`: a run pauses | 9 states |
| `NeverSteered`: a run's watcher delivers a message | 10 states |
| `NeverReplied`: a message is a paused run's reply | 17 states |
| `NeverResumed`: a paused run resumes | 18 states |
| `NeverRefused`: a claimant finds the thread claimed | 7 states |
| `NeverHandedOver`: a hand-over proceeds | 5 states |

## The actions, and the code they model

| Action | Code |
|---|---|
| `Send` | `Runner.send`, its `Workspace.commit` |
| `Direct` | `Workspace.commit` without the runner: a message, or a notice |
| `Answer` | `Runner.answer`, its `Workspace.commit`, then `Runner.resume` |
| `Retry` | `Runner.ask`, by a caller whose call raised or whose process died (ADR-0064) |
| `ReadHead` | `Runner.resume` and `Runner.ask`, their `head_seq` |
| `SaveAsk` | `Runner._ask`, its `save_cursor` |
| `ReadCursors` | `Runner._take`: `_taken_seq` and `cursor`, and the return when nothing is asked |
| `Acquire`, `Refused` | `Workspace.claim_thread`: `acquire_lease`, or `ThreadBusy`, on which `_take` returns |
| `Abandon` | `_abandon` |
| `Plan` | `Runner._plan` and `_resume`: resume, reply, a new run, or `save_cursor` with no message |
| `Reply` | `_reply`: a `Workspace.commit` with its cursor per open request |
| `RunStart`, `StartRefused` | `ArtifactWorkspace.wrap_run`'s `Workspace.record` of `RunStarted` with its cursor, which core's `_run_started` refuses for a run that is not paused |
| `Deliver` | `ArtifactWorkspace._watch` |
| `Finish`, `Stop`, `Fail` | `ArtifactWorkspace._finish` and `wrap_run`'s handlers, each a `Workspace.record` with its cursor, dropped by `_record` once the run was abandoned |
| `Interrupt`, `InterruptUnsaved` | a cancellation or failure in `Runner.send`, `Runner.ask`, `Runner.resume`, `_ask` or `_take`'s reads, before the claim |
| `FailClaimant` | `_take`'s handler around `_start`: a failure or cancellation at the claim, `_abandon`, `_plan` or `_reply` |
| `ClaimedAsInterrupted` | the same at `acquire_lease`, once SQL storage, which runs it to its end, took the lease |
| `FailStart` | `_run` and `_turn`, before `RunStarted` is recorded, cancelled by `_cancel_when_lost` too |
| `ReleaseInterrupted` | a cancellation at `release_lease`, which takes effect before it is raised |
| `Release` | `claim_thread`'s exit: `release_lease` |
| `HandOver` | `Runner._hand_over` and `_take_over` |
| `Crash`, `Restart` | a process that dies, and starts again with nothing in memory |
| `Tick`, `Renew`, `Lapse` | storage's clock, `Workspace._renew`, and its timer, `_lose` |

## What the spec assumes, and leaves out

- **Assumed atomic:** `_plan`'s reads (the cursors, the head, the paused runs, the log) are separate awaits in the code, while `Runner.answer` and direct commits write without the claim. The spec takes them as one step. So are `_take`'s two cursor reads; interleaved, they only make a hand-over more likely.
- **A lapse and a write in flight:** once a holder finds its claim lost, `_cancel_when_lost` cancels its run at the next await, so a write not yet begun never happens. `RunStart` stays enabled after `Lapse`: it stands for a write already in flight, which storage runs to its end. A claim can also lapse in storage with no `Lapse` at all, when another process's clock runs ahead ([#249](https://github.com/alexnodeland/lattice/issues/249)).
- **Calls run to their end:** both storages finish each call and raise a cancellation after it, so an interrupted ask is saved if its call reached the write, and a cancelled release still releases. A claim is taken and then raises on SQL storage only (`ClaimedAsInterrupted`); in-memory storage's lease calls never await. An unsaved ask (`InterruptUnsaved`) is a cancellation at the commit's end or at the authorization check that `Workspace.save_cursor` awaits first.
- **A process is one task:** a caller's call, then the hand-over it leads to, or a run's task, then its hand-over. Only a caller's call is cancelled before it starts a run: `Runner.aclose` alone cancels a hand-over, and it is left out.
- **Left out:** a hand-over that raises, which `_take_over` logs and drops, leaving what was asked to the next command; a failure in `Session.start`, under the claim but before the run's task, which hands over with what `_take` read where the spec uses what the plan read; authorization and one author per turn (ADR-0057), so every message is one author's; the agent's own messages; and I7, the upgrade point, a migration's property that `test_upgrade.py` holds.

## What TLC found

Each trace is the shortest TLC found with a configuration's constants changed as the finding says, and its property checked alone. Findings 1 to 4 each have a test in `packages/artifactr/tests/agent/test_invariants.py` that runs the trace against the code, marked as a strict `xfail` until it is fixed.

1. **A claim that lapses while its holder lives lets two runs take the same prompt** (`ThreadClaim.cfg` with `Stalls = TRUE`: `I1_ConsumedAtMostOnce`, and `I3_OneActiveRun`; 16 states; [#249](https://github.com/alexnodeland/lattice/issues/249)). Process 1 claims the thread and plans a run for a message. Its claim lapses in storage before it records `run_started`. Process 2 claims the thread, finds no run to abandon and `taken` unchanged, and plans a run for the same message. Both writes commit: the message is consumed twice and two runs are active. ADR-0055 allows one exception to I1 when a claim lapses, steering delivered again; this is a second. The tests reproduce it with a storage clock that runs ahead.
2. **A cancelled claim on SQL storage leaves a claim no task releases** (`ThreadClaimLive.cfg` with `MaxFaults = 1`: `I3_ClaimHasATask` in 5 states, and `AskedIsTaken` with `Retries = TRUE` too; [#250](https://github.com/alexnodeland/lattice/issues/250)). A send's claimant is cancelled at `acquire_lease`, which SQL storage runs to its end before it raises the cancellation. `claim_thread` raises before its `try`, so it never releases the lease. The claimant's hand-over, and every command until the lease lapses, find the thread busy and return.
3. **A send cancelled after its ask, before it claims, hands nothing over** (`ThreadClaimLive.cfg` with `MaxFaults = 1`: `I3_NoStrandedAsk` in 3 states, and `AskedIsTaken`; [#251](https://github.com/alexnodeland/lattice/issues/251)). `_take`'s cursor reads come before the `try` that hands over, so the message is left asked, untaken and the thread free, until the thread's next command.
4. **A message asked while its thread's holder dies waits for the next command** (`ThreadClaimLive.cfg` with `MaxCrashes = 1` and `Retries = TRUE`: `AskedIsTaken`, 12 states; [#252](https://github.com/alexnodeland/lattice/issues/252)). ADR-0055 designs this: a dead process's run waits for its thread's next claim, and so does what was asked meanwhile. It is filed for a decision, since `Sent.run`'s docstring promises a hand-over.
5. **A crash gives a dead run's steering to a model again** (`I1_GivenOnce` without its crash guard, at `ThreadClaim.cfg`'s bounds: 18 states; [#257](https://github.com/alexnodeland/lattice/issues/257)). `taken` is saved with the run's end, so steering a dead run was given is taken again by the next turn. ADR-0055's one exception names a lapse, not a crash; filed for the record to say so, or for the code to change. It has no test yet.
6. **A message committed, whose ask is lost, is never taken unless its caller asks again** (`ThreadClaimLive.cfg` with `MaxFaults = 1`: `SentIsTaken`, 5 states). This is [ADR-0045](../adr/0045-a-message-id-is-used-once.md)'s known hole, and [ADR-0064](../adr/0064-asking-for-a-threads-next-turn.md)'s `Runner.ask` is its fix, for a caller that uses it. With `Retries = TRUE` as well, TLC finds it only through finding 2.

## When the protocol changes

A change to the claim, the cursors, planning, the hand-over or a run's start and end changes the spec in the same pull request, and the pull request template asks. When a fix lands for a finding, its test loses its `xfail`, and its property joins a configuration with the setting that found it.
