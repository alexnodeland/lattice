# artifactr's thread claim, in TLA+

[`ThreadClaim.tla`](ThreadClaim.tla) models how artifactr's `Runner` claims a thread and decides its turns ([ADR-0055](../adr/0055-turns-from-the-log.md)), as the code is, and TLC checks it ([lattice ADR-0025](../../adr/0025-formal-specs-in-tla-and-lean.md)). It is the first of lattice's formal specs.

It models one thread and a few processes that send, ask, claim, plan, run and hand over. The claim is a lease that lapses, and a clock ticks it down as an action of its own. The `asked` and `taken` cursors are durable, and so is the log. Processes crash, fail and are cancelled at each of the code's awaits, and send at the same time.

## What a run of TLC shows

TLC explores every behaviour within the bounds each `.cfg` sets, and no other. A property that holds there is a small-scope claim, not a proof: many concurrency bugs already show with two processes and two messages, but nothing beyond the bounds is checked. A property TLC finds violated is a real behaviour of the model, with the trace to show it. It is a bug of the code if the model is the code, which the action table below argues, step by step.

| Configuration | Where it runs | Bounds | Checks |
|---|---|---|---|
| [`ThreadClaim.cfg`](ThreadClaim.cfg) | CI, when the spec or artifactr changes | 2 processes, 2 messages or notices, a pause, a failure or cancellation, a crash | I1, I2, I3's one active run, I4, I5, I6 |
| [`ThreadClaimLive.cfg`](ThreadClaimLive.cfg) | CI, likewise | 2 processes, 2 messages or notices, a pause; nothing fails, is cancelled or crashes | I3's claim and hand-over, and that what is asked or sent is taken |
| [`ThreadClaimDeep.cfg`](ThreadClaimDeep.cfg) | Nightly | 3 messages or notices, and a TTL of 2 ticks, so a live holder renews its claim; otherwise the live run's | The live run's properties, deeper |

No configuration lets a claim lapse while its holder lives (`Stalls = FALSE`), and the live ones have no fault at all. Those are where TLC finds the bugs below: the configurations check what holds of the code today, so CI stays green, and each finding's issue says how to check its fix. At a TTL of one tick, the pull request's runs never renew a claim; Nightly's does. CI runs TLC with `scripts/tlc`, which downloads `tla2tools.jar` 1.7.4 and checks its SHA-256 first.

## The properties

Each is named after the ADR-0055 invariant it checks, and tied to a test that holds the code to the same invariant. `scripts/check_spec.py` fails if the spec's header table, these names, the configurations and the tests disagree.

| Property | ADR-0055 | Test | Kind | At the bounds |
|---|---|---|---|---|
| `I1_ConsumedAtMostOnce` | I1 | `test_i1_messages_sent_at_once_from_two_processes_are_each_consumed_once` | invariant | Holds; **violated when a claim lapses while its holder lives** ([#249](https://github.com/alexnodeland/lattice/issues/249)) |
| `I1_NoneSkipped` | I1 | `test_i1_a_message_sent_as_a_run_releases_its_thread_is_consumed_once` | invariant | Holds, with lapses too |
| `I1_GivenOnce` | I1 | `test_i2_steering_is_consumed_with_the_runs_end` | invariant | Holds, outside ADR-0055's one exception and crashes |
| `I2_ConsumedWithItsWrite` | I2 | `test_i2_a_prompt_is_consumed_with_its_runs_start` | action property | Holds |
| `I3_ClaimHasATask` | I3 | `test_i3_a_claim_is_released_when_its_run_cannot_be_set_up` | invariant | Holds without faults; **violated by a claim call that is interrupted** ([#250](https://github.com/alexnodeland/lattice/issues/250)) |
| `I3_NoStrandedAsk` | I3 | `test_i3_a_command_that_asked_before_its_holder_read_is_handed_over` | invariant | Holds without faults; **violated by a cancellation after the ask** ([#251](https://github.com/alexnodeland/lattice/issues/251)) |
| `I3_OneActiveRun` | I3 | `test_a_thread_is_claimed_by_one_run_at_a_time` | invariant | Holds; **violated when a claim lapses while its holder lives** ([#249](https://github.com/alexnodeland/lattice/issues/249)) |
| `I4_NothingTakenUnstarted` | I4 | `test_i4_a_turn_that_keeps_failing_before_it_starts_consumes_nothing` | action property | Holds, by the actions' construction |
| `I5_DirectAsksNothing` | I5 | `test_i5_a_message_committed_directly_starts_no_turn_and_the_next_consumes_it` | action property | Holds, by the actions' construction |
| `I6_OldestIsTheReply` | I6 | `test_i6_a_message_committed_directly_in_a_paused_thread_is_its_reply` | action property | Holds |
| `AskedIsTaken` | I1, I3 | `test_i3_a_message_left_to_a_holder_that_never_starts_is_handed_over` | liveness | Holds without faults; **violated by a cancellation, an interrupted claim, or a crash** ([#250](https://github.com/alexnodeland/lattice/issues/250), [#251](https://github.com/alexnodeland/lattice/issues/251), [#252](https://github.com/alexnodeland/lattice/issues/252)) |
| `SentIsTaken` | I1, I5 | `test_i5_a_message_whose_ask_was_lost_is_consumed_once_its_thread_is_asked` | liveness | Holds without faults; **violated between a send's commit and its ask**, ADR-0045's known hole, unless the caller asks again (ADR-0064) |

I4 and I5 hold by how the actions are written: they guard the spec against an edit that breaks them, not the code. I2 is weaker than ADR-0055's prose, as the code is: a plan that finds no message to carry out saves `taken` in a write of its own ([`_plan`](https://github.com/alexnodeland/lattice/blob/main/packages/artifactr/src/artifactr/agent/runner.py)), which consumes nothing. The liveness properties assume nothing *fails* (a failure that consumed nothing hands over only a newer ask, by I4's design); cancellations and crashes may happen. I7, the upgrade point, is a migration's property, and `test_upgrade.py` holds it.

## The actions, and the code they model

Links are to [`runner.py`](https://github.com/alexnodeland/lattice/blob/main/packages/artifactr/src/artifactr/agent/runner.py), [`workspace.py`](https://github.com/alexnodeland/lattice/blob/main/packages/artifactr/src/artifactr/workspace/workspace.py), [`capability.py`](https://github.com/alexnodeland/lattice/blob/main/packages/artifactr/src/artifactr/agent/capability.py) and core's [`rules.py`](https://github.com/alexnodeland/lattice/blob/main/packages/artifactr/src/artifactr/core/rules.py).

| Action | Code |
|---|---|
| `Send` | `Runner.send`: `workspace.commit(PostMessage)` |
| `Direct` | `Workspace.commit` without the runner: a message, or a notice |
| `Answer` | `Runner.answer`: `workspace.commit(AnswerDeferred)`, then `Runner.resume` |
| `Retry` | `Runner.ask`, by a caller whose call raised or whose process died (ADR-0064) |
| `ReadHead` | `Runner.resume` and `Runner.ask`: `head_seq()` |
| `SaveAsk` | `Runner._ask`: `save_cursor(asked)` |
| `ReadCursors` | `Runner._take`: `_taken_seq`, `cursor(asked)`, and the return when nothing is asked |
| `Acquire`, `Refused` | `Workspace.claim_thread`: `acquire_lease`, or `ThreadBusy`, which `_take` returns on |
| `Abandon` | `_abandon` |
| `Plan` | `Runner._plan`, and `_resume`: resume, reply, a new run, or `save_cursor(taken)` with no message |
| `Reply` | `_reply`: one `commit(AnswerDeferred, cursor=...)` per open request |
| `RunStart`, `StartRefused` | `Capability.wrap_run`'s `record(RunStarted, cursor=...)`, which core's `_run_started` refuses for a run that is not paused |
| `Deliver` | `Capability._watch` |
| `Finish`, `Stop`, `Fail` | `Capability._finish` and `wrap_run`'s handlers: `record(RunPaused / RunEnded, cursor=...)`, dropped by `_record` once the run was abandoned |
| `Interrupt`, `InterruptUnsaved` | a cancellation or failure in `send`, `ask`, `resume`, `_ask` or `_take`'s reads, before the claim; the ask's write may have taken effect |
| `FailClaimant` | `_take`'s handler around `_start`: a failure or cancellation at the claim, `_abandon`, `_plan` or `_reply` |
| `ClaimedAsInterrupted` | the same at `acquire_lease`, which the storage granted: `claim_thread` releases only a claim it returned |
| `FailStart` | `_run` and `_turn`, before `run_started` is recorded, cancelled by `_cancel_when_lost` too |
| `ReleaseInterrupted` | a cancellation at `release_lease`, which may not have taken effect |
| `Release` | `claim_thread`'s exit: `release_lease` |
| `HandOver` | `Runner._hand_over` and `_take_over` |
| `Crash`, `Restart` | a process that dies, and starts again with nothing in memory |
| `Tick`, `Renew`, `Lapse` | storage's clock, `Workspace._renew`, and its timer `_lose` |

Each process does one thing at a time: a run's task, then its hand-over, as in the code; a caller's call, or the hand-over it leads to. Each of `_plan`'s reads and `_take`'s two cursor reads are one step here: interleaved, they only make a hand-over more likely. A failure in `Session.start`, under the claim but before the run's task, hands over with what `_take` read, where the spec uses what the plan read; the two differ only in which hand-over proceeds. Left out: authorization and one author per turn (ADR-0057), the agent's own messages, `Runner.aclose`, and I7.

## What TLC found

Each trace is the shortest TLC found, with a configuration's constants changed as each finding says, and its property checked alone.

1. **A claim that lapses while its holder lives lets two runs take the same prompt** (`ThreadClaim.cfg` with `Stalls = TRUE`: `I1_ConsumedAtMostOnce`, and `I3_OneActiveRun`; [#249](https://github.com/alexnodeland/lattice/issues/249)). Two messages are sent. Process 1 claims the thread and plans a run for the first. Its claim lapses before it records `run_started`, as when the write stalls. Process 2 claims the thread, finds no run to abandon and `taken` unchanged, and plans a run for the same message. Both writes commit: the message is consumed twice and two runs are active. ADR-0055 allows one exception to I1 when a claim lapses, steering delivered again; this is a second. Nothing in the consuming write checks that its claim still holds.
2. **A claim call that is interrupted after the storage granted it leaves a claim no task releases** (`ThreadClaimLive.cfg` with `MaxFaults = 1`: `I3_ClaimHasATask`, and `AskedIsTaken` with `Retries = TRUE` too; [#250](https://github.com/alexnodeland/lattice/issues/250)). A send's claimant is cancelled at `acquire_lease`, which the `Storage` protocol allows to have taken effect. `claim_thread` releases only a claim it returned, so the lease stays until it lapses. The claimant's hand-over, and any command until the lease lapses, find the thread busy and return, relying on a holder's hand-over that will not come. A cancelled `release_lease` does the same.
3. **A send or ask cancelled after its ask is saved, before it claims, hands nothing over** (`ThreadClaimLive.cfg` with `MaxFaults = 1`: `I3_NoStrandedAsk`, and `AskedIsTaken`; [#251](https://github.com/alexnodeland/lattice/issues/251)). `_take`'s two cursor reads come before the `try` that hands over, so a cancellation there, or at the ask's own write once it took effect, leaves the message asked, untaken, and the thread free, until the thread's next command.
4. **A message asked while a process that then dies holds the thread waits for the next command** (`ThreadClaimLive.cfg` with `MaxCrashes = 1` and `Retries = TRUE`: `AskedIsTaken`; [#252](https://github.com/alexnodeland/lattice/issues/252)). The holder dies after its plan, once its caller's call has returned the run; nothing looks at the thread when its claim lapses or the process restarts. A caller that asks again, as ADR-0064 asks, is refused while the dead claim lives, and returns.
5. **A message committed, whose ask is lost, is never taken unless its caller asks again** (`ThreadClaimLive.cfg` with `MaxFaults = 1`: `SentIsTaken`). A send cancelled between its commit and its ask leaves its message unasked. This is [ADR-0045](../adr/0045-a-message-id-is-used-once.md)'s known hole, and [ADR-0064](../adr/0064-asking-for-a-threads-next-turn.md)'s `Runner.ask` is its fix, for a caller that uses it. With `Retries = TRUE` as well, TLC finds it only through finding 2.

## When the protocol changes

A change to the claim, the cursors, planning, the hand-over or a run's start and end changes the spec in the same pull request, and the pull request template asks. When a fix lands for one of the findings, its property moves into a CI configuration, with the setting that found it.
