---------------------------- MODULE ThreadClaim ----------------------------
\* artifactr's thread claim and turn protocol (artifactr ADR-0055), as the code is: one thread,
\* processes that send, ask, claim, plan, run and hand over, a lease that lapses, the durable
\* `asked` and `taken` cursors, and crashes, failures and cancellations at the code's awaits.
\* README.md maps each action to its function, and says what TLC found.
\*
\* Each property is named after the ADR-0055 invariant it checks, and tied to a test that holds
\* the code to it. scripts/check_spec.py fails when this table, the .cfg files, the README and
\* the tests disagree.
\*
\* Property                 | ADR-0055 | Test
\* I1_ConsumedAtMostOnce    | I1       | test_i1_messages_sent_at_once_from_two_processes_are_each_consumed_once
\* I1_NoneSkipped           | I1       | test_i1_a_message_sent_as_a_run_releases_its_thread_is_consumed_once
\* I1_GivenOnce             | I1, I2   | test_i2_steering_is_consumed_with_the_runs_end
\* I2_ConsumedWithItsWrite  | I2       | test_i2_a_prompt_is_consumed_with_its_runs_start
\* I3_ClaimHasATask         | I3       | test_i3_a_claim_is_released_when_its_run_cannot_be_set_up
\* I3_NoStrandedAsk         | I3       | test_i3_a_command_that_asked_before_its_holder_read_is_handed_over
\* I3_OneActiveRun          | I3       | test_i3_a_claim_that_lapses_as_its_run_starts_leaves_one_run
\* I4_NothingTakenUnstarted | I4       | test_i4_a_turn_that_keeps_failing_before_it_starts_consumes_nothing
\* I5_DirectAsksNothing     | I5       | test_i5_a_message_committed_directly_starts_no_turn_and_the_next_consumes_it
\* I6_OldestIsTheReply      | I6       | test_i6_a_message_committed_directly_in_a_paused_thread_is_its_reply
\* AskedIsTaken             | I1, I3   | test_i3_a_message_left_to_a_holder_that_never_starts_is_handed_over
\* SentIsTaken              | I1, I5   | test_i5_a_message_whose_ask_was_lost_is_consumed_once_its_thread_is_asked
\*
\* Not modelled: I7, the upgrade point, a migration's property that test_upgrade.py holds. Also
\* left out: authorization and one author per turn (ADR-0057), so every message is one author's;
\* the agent's own messages; Runner.aclose, and cancelling a Runner.drain, the only ways to
\* cancel a hand-over; a hand-over or a look again that raises, which the runner logs and drops,
\* leaving what was asked to the next command; and a process's concurrent tasks: each process here
\* is one task at a time, and a crash ends it, beside a refused claimant's look, which waits in
\* the background; and a process that starts again sweeps the thread before anything else.
EXTENDS Naturals, Sequences, FiniteSets

CONSTANTS
    Procs,       \* the processes that share the thread
    MaxLog,      \* messages and notices committed in a behaviour, at most
    MaxReq,      \* the requests a run pauses on
    MaxPauses,   \* pauses in a behaviour, at most
    TTL,         \* a claim's ticks to live, from its last renewal
    MaxCrashes,  \* process crashes in a behaviour, at most
    MaxFaults,   \* failures and cancellations in a behaviour, at most
    Stalls,      \* whether a live holder may stall past its TTL, so its claim lapses
    Retries      \* whether a caller whose call raised, or whose process died, asks again

ASSUME /\ Procs # {} /\ MaxLog \in Nat /\ MaxReq \in Nat \ {0} /\ MaxPauses \in Nat
       /\ TTL \in Nat \ {0} /\ MaxCrashes \in Nat /\ MaxFaults \in Nat
       /\ Stalls \in BOOLEAN /\ Retries \in BOOLEAN

MaxSeq == MaxLog + MaxReq * MaxPauses   \* the log's longest: what is committed, and answers

VARIABLES
    log,      \* the thread's log: "sent" (by Runner.send), "direct", "notice" or "answer"
    asked,    \* the durable cursor: how far messages and answers asked for a turn
    taken,    \* the durable cursor: how far turns have taken the log
    runs,     \* the thread's runs, in the order they started
    lease,    \* the claim in storage: its owner, or "none", and its ticks to live
    \* What happened, for the properties.
    count,    \* for each log entry, how many writes recorded it as consumed
    effects,  \* for each log entry, how many times a model was given it
    crashes,  \* processes that died
    faults,   \* failures and cancellations
    failed,   \* whether one of them was a failure, not a cancellation
    lapsed,   \* whether a claim lapsed while its holder lived
    \* Each process's own.
    pc,       \* its step
    lost,     \* whether its claim is lost, as its renewal's timer found
    rd,       \* the cursors its claimant read before it claimed
    plan,     \* the turn it planned
    dlv,      \* how far its run's watcher has delivered
    nxt,      \* what it does once it has released the thread: "loop", "handover" or "return"
    snap,     \* the cursors, and whether it was cancelled, that its hand-over compares with
    askVal,   \* what it will save as asked
    owe,      \* its caller's call: "call" while it runs, "owed" once it raised or its process
              \* died, "no" once it returned or there was none
    looking   \* whether a claimant it refused is to look at the thread again (Runner._retake)

shared == <<log, asked, taken, runs>>
audit  == <<count, effects, crashes, faults, failed, lapsed>>
local  == <<pc, lost, rd, plan, dlv, nxt, snap, askVal, owe, looking>>
vars   == <<shared, lease, audit, local>>

Free == [owner |-> "none", ttl |-> 0]
Max(a, b) == IF a > b THEN a ELSE b
SetMin(S) == CHOOSE x \in S : \A y \in S : x <= y
Bump(f, S) == [i \in DOMAIN f |-> IF i \in S THEN f[i] + 1 ELSE f[i]]
Step(p, v) == pc' = [pc EXCEPT ![p] = v]

\* The steps at which a process holds the claim it made.
Holding == {"abandoning", "planning", "replying", "starting", "running", "releasing"}

Msg(i) == i \in 1..Len(log) /\ log[i] \in {"sent", "direct"}
Range(lo, hi) == {i \in lo + 1 .. hi : Msg(i)}   \* the messages in (lo, hi]
Untaken == Range(taken, Len(log))
Committed == Len(SelectSeq(log, LAMBDA e : e # "answer"))

\* Storage grants a claim that is free or has expired: it knows nothing of its holder's health.
Acquirable == lease = Free \/ lease.ttl = 0
\* The claim in storage is the one p's current task holds; Live, if p has not found it lost.
Mine(p) == lease.owner = p /\ pc[p] \in Holding
Live(p) == Mine(p) /\ ~lost[p]

Paused == {r \in DOMAIN runs : runs[r].st = "paused"}
PausedRun == CHOOSE r \in Paused : \A s \in Paused : s <= r   \* runner.py takes paused[-1]
Pauses == LET sum[i \in 0..Len(runs)] == IF i = 0 THEN 0 ELSE sum[i - 1] + runs[i].pause
          IN sum[Len(runs)]

NoPlan == [kind |-> "none", run |-> 0, lo |-> 0, hi |-> 0, msg |-> 0, pause |-> 0,
           tt |-> 0, ta |-> 0, done |-> FALSE]
NoSnap == [t |-> 0, a |-> 0, c |-> FALSE]

Init ==
    /\ log = <<>> /\ asked = 0 /\ taken = 0 /\ runs = <<>> /\ lease = Free
    /\ count = [i \in 1..MaxSeq |-> 0] /\ effects = [i \in 1..MaxSeq |-> 0]
    /\ crashes = 0 /\ faults = 0 /\ failed = FALSE /\ lapsed = FALSE
    /\ pc = [p \in Procs |-> "idle"] /\ lost = [p \in Procs |-> FALSE]
    /\ rd = [p \in Procs |-> NoSnap] /\ plan = [p \in Procs |-> NoPlan]
    /\ dlv = [p \in Procs |-> 0] /\ nxt = [p \in Procs |-> "loop"]
    /\ snap = [p \in Procs |-> NoSnap] /\ askVal = [p \in Procs |-> 0]
    /\ owe = [p \in Procs |-> "no"] /\ looking = [p \in Procs |-> FALSE]

\* A cancellation (c) or a failure, within the behaviour's budget.
Fault(c) == /\ faults < MaxFaults /\ faults' = faults + 1 /\ failed' = (failed \/ ~c)

\* Only a caller's call is cancelled before it starts a run: a hand-over is cancelled only by
\* Runner.aclose, or by cancelling a Runner.drain, which cancels the hand-overs it waits for; both
\* are left out.
Cancellable(p, c) == c => owe[p] = "call"

\* The caller's call returns: a hand-over's steps return to no caller.
Returned(p) == owe' = [owe EXCEPT ![p] = IF @ = "call" THEN "no" ELSE @]

-----------------------------------------------------------------------------
\* Callers. A message, or an answer, is committed, and then asked for: two writes.

\* Runner.send: commit the message.
Send(p) ==
    /\ pc[p] = "idle" /\ Committed < MaxLog
    /\ log' = Append(log, "sent")
    /\ askVal' = [askVal EXCEPT ![p] = Len(log')] /\ owe' = [owe EXCEPT ![p] = "call"]
    /\ Step(p, "asking")
    /\ UNCHANGED <<asked, taken, runs, lease, audit, lost, rd, plan, dlv, nxt, snap, looking>>

\* Workspace.commit, without the runner: a message, or a notice. It asks for nothing.
Direct(kind) ==
    /\ Committed < MaxLog
    /\ log' = Append(log, kind)
    /\ UNCHANGED <<asked, taken, runs, lease, audit, local>>

\* Runner.answer: commit an answer to a paused run's request; Runner.resume then reads the head.
Answer(p) ==
    /\ pc[p] = "idle" /\ Paused # {} /\ runs[PausedRun].open > 0
    /\ log' = Append(log, "answer")
    /\ runs' = [runs EXCEPT ![PausedRun].open = @ - 1]
    /\ owe' = [owe EXCEPT ![p] = "call"]
    /\ Step(p, "head")
    /\ UNCHANGED <<asked, taken, lease, audit, lost, rd, plan, dlv, nxt, snap, askVal, looking>>

\* Runner.ask: a caller whose call raised, or whose process died, asks again (ADR-0064).
Retry(p) ==
    /\ Retries /\ pc[p] = "idle" /\ owe[p] # "no"
    /\ owe' = [owe EXCEPT ![p] = "call"]
    /\ Step(p, "head")
    /\ UNCHANGED <<shared, lease, audit, lost, rd, plan, dlv, nxt, snap, askVal, looking>>

\* Runner.resume and Runner.ask: read the log's head, to ask for it.
ReadHead(p) ==
    /\ pc[p] = "head"
    /\ askVal' = [askVal EXCEPT ![p] = Len(log)]
    /\ Step(p, "asking")
    /\ UNCHANGED <<shared, lease, audit, lost, rd, plan, dlv, nxt, snap, owe, looking>>

\* Runner._take: save the ask. It has read nothing yet.
SaveAsk(p) ==
    /\ pc[p] = "asking"
    /\ asked' = Max(asked, askVal[p])
    /\ rd' = [rd EXCEPT ![p] = NoSnap]
    /\ Step(p, "reading")
    /\ UNCHANGED <<log, taken, runs, lease, audit, lost, plan, dlv, nxt, snap, askVal, owe,
                   looking>>

-----------------------------------------------------------------------------
\* Runner._take, _start and _plan: a claimant.

\* _take: read both cursors; with nothing asked beyond taken, return.
ReadCursors(p) ==
    /\ pc[p] = "reading"
    /\ rd' = [rd EXCEPT ![p] = [t |-> taken, a |-> asked, c |-> FALSE]]
    /\ IF asked <= taken
          THEN Step(p, "idle") /\ Returned(p)
          ELSE Step(p, "claiming") /\ UNCHANGED owe
    /\ UNCHANGED <<shared, lease, audit, lost, plan, dlv, nxt, snap, askVal, looking>>

\* Workspace.claim_thread: acquire the lease, under a holder of the claim's own.
Acquire(p) ==
    /\ pc[p] = "claiming" /\ Acquirable
    /\ lease' = [owner |-> p, ttl |-> TTL]
    /\ lost' = [lost EXCEPT ![p] = FALSE]
    /\ Step(p, "abandoning")
    /\ UNCHANGED <<shared, audit, rd, plan, dlv, nxt, snap, askVal, owe, looking>>

\* ThreadBusy: _take returns, leaving the thread to its holder's hand-over, and Runner._retake
\* has the process look again once the claim could have lapsed, should its holder have died.
Refused(p) ==
    /\ pc[p] = "claiming" /\ ~Acquirable
    /\ Step(p, "idle") /\ Returned(p)
    /\ looking' = [looking EXCEPT ![p] = TRUE]
    /\ UNCHANGED <<shared, lease, audit, lost, rd, plan, dlv, nxt, snap, askVal, looking>>

\* Runner._take_again: a claim_ttl after the refusal, a holder that lives has renewed its claim or
\* released it, and one that died has let it lapse. A look refused again, by a live holder, is
\* left out as a stutter: this step waits until the claim can be taken, or what was asked is
\* taken, and then reads again. The process is one task, so it looks while it is idle.
LookAgain(p) ==
    /\ looking[p] /\ pc[p] = "idle" /\ (Acquirable \/ asked <= taken)
    /\ looking' = [looking EXCEPT ![p] = FALSE]
    /\ rd' = [rd EXCEPT ![p] = NoSnap]
    /\ Step(p, "reading")
    /\ UNCHANGED <<shared, lease, audit, lost, plan, dlv, nxt, snap, askVal, owe, looking>>

\* _abandon: each run still running is recorded as failed, "abandoned".
Abandon(p) ==
    /\ pc[p] = "abandoning"
    /\ runs' = [r \in DOMAIN runs |->
                  IF runs[r].st = "running" THEN [runs[r] EXCEPT !.st = "failed"] ELSE runs[r]]
    /\ Step(p, "planning")
    /\ UNCHANGED <<log, asked, taken, lease, audit, lost, rd, plan, dlv, nxt, snap, askVal, owe,
                   looking>>

\* _plan: decide, holding the thread, which turn takes the oldest message not taken. Assumed
\* atomic: _plan reads the cursors, the head, the paused runs and the log in separate awaits,
\* while Runner.answer and direct commits write without the claim; the spec takes the reads as
\* one step.
Plan(p) ==
    /\ pc[p] = "planning"
    /\ LET head == Len(log)
           turn(kind, run, lo, hi, msg) ==
               [kind |-> kind, run |-> run, lo |-> lo, hi |-> hi, msg |-> msg,
                pause |-> IF run = 0 THEN 0 ELSE runs[run].pause,
                tt |-> taken, ta |-> asked, done |-> FALSE]
           \* A turn is planned, and the caller's call returns its run.
           start(t, next) == /\ plan' = [plan EXCEPT ![p] = t] /\ Step(p, next)
                             /\ Returned(p) /\ UNCHANGED <<taken, nxt, looking>>
           \* Nothing is planned: release the thread, and look again.
           again == /\ Step(p, "releasing") /\ nxt' = [nxt EXCEPT ![p] = "loop"]
                    /\ UNCHANGED <<plan, owe, looking>>
       IN \/ /\ asked <= taken                                \* what was asked is taken
             /\ again /\ UNCHANGED taken
          \/ /\ asked > taken /\ Paused # {} /\ runs[PausedRun].open = 0
             /\ start(turn("resume", PausedRun, taken, head, 0), "starting")
          \/ /\ asked > taken /\ Paused # {} /\ runs[PausedRun].open > 0 /\ Untaken # {}
             /\ start(turn("reply", PausedRun, taken, 0, SetMin(Untaken)), "replying")
          \/ /\ asked > taken /\ Paused = {} /\ Untaken # {}
             /\ start(turn("new", 0, taken, SetMin(Untaken), 0), "starting")
          \/ /\ asked > taken /\ Untaken = {}                 \* no message to carry out
             /\ Paused # {} => runs[PausedRun].open > 0
             /\ taken' = Max(taken, head)                    \* in a write of its own
             /\ again
    /\ UNCHANGED <<log, asked, runs, lease, audit, lost, rd, dlv, snap, askVal, looking>>

\* An answer the plan's reply would commit now.
Answering(p) ==
    LET r == plan[p].run
    IN runs[r].st = "paused" /\ runs[r].pause = plan[p].pause /\ runs[r].open > 0

\* _reply: an answer to each open request, each in its own write, which takes the message and is
\* fenced by the claim. Once none is open, the run resumes if the message answered one; if not,
\* the holder plans again.
Reply(p) ==
    /\ pc[p] = "replying"
    /\ Answering(p) => lease.owner = p
    /\ LET t == plan[p]
           r == t.run
       IN IF Answering(p)
             THEN /\ log' = Append(log, "answer")
                  /\ runs' = [runs EXCEPT ![r].open = @ - 1]
                  /\ taken' = Max(taken, t.msg)
                  /\ count' = IF t.done THEN count ELSE Bump(count, {t.msg})
                  /\ effects' = IF t.done THEN effects ELSE Bump(effects, {t.msg})
                  /\ plan' = [plan EXCEPT ![p].done = TRUE]
                  /\ UNCHANGED pc
             ELSE /\ IF t.done
                        THEN /\ plan' = [plan EXCEPT ![p] = [t EXCEPT !.kind = "resume",
                                                                  !.lo = t.msg, !.hi = t.msg]]
                             /\ Step(p, "starting")
                        ELSE Step(p, "planning") /\ UNCHANGED plan
                  /\ UNCHANGED <<log, runs, taken, count, effects>>
    /\ UNCHANGED <<asked, lease, crashes, faults, failed, lapsed, lost, rd, dlv, nxt, snap, askVal,
                   owe, looking>>

\* The answer's fence refuses it: another claimant has the thread. ThreadBusy propagates from
\* _plan, the claim is released, and _take returns, leaving the thread to that claimant.
ReplyFenced(p) ==
    /\ pc[p] = "replying" /\ Answering(p) /\ lease.owner # p
    /\ Step(p, "releasing") /\ nxt' = [nxt EXCEPT ![p] = "return"]
    /\ UNCHANGED <<shared, lease, audit, lost, rd, plan, dlv, snap, askVal, owe, looking>>

-----------------------------------------------------------------------------
\* A run: Capability.wrap_run's start, its watcher, and its end.

\* Record run_started with the taken cursor, in one write, fenced by the claim: it commits only
\* while the claim in storage is p's, lapsed or not (ADR-0069). Core refuses a resume unless its
\* run is paused. Once the claim is found lost, the run is cancelled at its next await, so a write
\* not yet begun never happens; this step stays enabled after Lapse, which stands for a write
\* already in flight. A lapse in storage needs no Lapse step at all: another process's clock may
\* run ahead, and the fence alone keeps the write from a claim another claimant took.
RunStart(p) ==
    /\ pc[p] = "starting" /\ lease.owner = p
    /\ LET t == plan[p]
           r == IF t.kind = "new" THEN Len(runs) + 1 ELSE t.run
       IN /\ IF t.kind = "new" THEN TRUE ELSE runs[r].st = "paused"
          /\ runs' = IF t.kind = "new"
                        THEN Append(runs, [st |-> "running", open |-> 0, pause |-> 0])
                        ELSE [runs EXCEPT ![r].st = "running"]
          /\ plan' = [plan EXCEPT ![p].run = r]
          /\ taken' = Max(taken, t.hi)
          /\ count' = Bump(count, Range(t.lo, t.hi))
          /\ effects' = Bump(effects, Range(t.lo, t.hi))
          /\ dlv' = [dlv EXCEPT ![p] = t.hi]
    /\ Step(p, "running")
    /\ UNCHANGED <<log, asked, lease, crashes, faults, failed, lapsed, lost, rd, nxt, snap, askVal,
                   owe, looking>>

\* Core refuses the resume's run_started: the run fails before it starts.
StartRefused(p) ==
    /\ pc[p] = "starting" /\ plan[p].kind # "new" /\ runs[plan[p].run].st # "paused"
    /\ snap' = [snap EXCEPT ![p] = [t |-> plan[p].tt, a |-> plan[p].ta, c |-> FALSE]]
    /\ failed' = TRUE
    /\ Step(p, "releasing") /\ nxt' = [nxt EXCEPT ![p] = "handover"]
    /\ UNCHANGED <<shared, lease, count, effects, crashes, faults, lapsed, lost, rd, plan, dlv,
                   askVal, owe, looking>>

\* The fence refuses run_started: another claimant took the claim. The run fails before it starts,
\* and hands over with what its plan read.
StartFenced(p) ==
    /\ pc[p] = "starting" /\ lease.owner # p
    /\ snap' = [snap EXCEPT ![p] = [t |-> plan[p].tt, a |-> plan[p].ta, c |-> FALSE]]
    /\ Step(p, "releasing") /\ nxt' = [nxt EXCEPT ![p] = "handover"]
    /\ UNCHANGED <<shared, lease, audit, lost, rd, plan, dlv, askVal, owe, looking>>

\* The watcher gives the run the log's next entry; the run records it only at its end.
Deliver(p) ==
    /\ pc[p] = "running" /\ dlv[p] < Len(log)
    /\ dlv' = [dlv EXCEPT ![p] = @ + 1]
    /\ effects' = IF Msg(dlv[p] + 1) THEN Bump(effects, {dlv[p] + 1}) ELSE effects
    /\ UNCHANGED <<shared, lease, count, crashes, faults, failed, lapsed, pc, lost, rd, plan, nxt,
                   snap, askVal, owe, looking>>

\* The run's end, recorded with the taken cursor in one write. An end that the run's abandonment
\* came before is refused, and dropped (capability.py's _record).
End(p, outcome) ==
    /\ LET t == plan[p]
           recorded == runs[t.run].st = "running"
       IN /\ runs' = IF recorded
                        THEN [runs EXCEPT ![t.run] = [st |-> outcome,
                                  open |-> IF outcome = "paused" THEN MaxReq ELSE 0,
                                  pause |-> IF outcome = "paused" THEN @.pause + 1 ELSE @.pause]]
                        ELSE runs
          /\ taken' = IF recorded THEN Max(taken, dlv[p]) ELSE taken
          /\ count' = IF recorded THEN Bump(count, Range(t.hi, dlv[p])) ELSE count
          /\ snap' = [snap EXCEPT ![p] = [t |-> t.tt, a |-> t.ta, c |-> outcome = "stopped"]]
    /\ Step(p, "releasing") /\ nxt' = [nxt EXCEPT ![p] = "handover"]
    /\ UNCHANGED <<log, asked, lease, effects, crashes, lapsed, lost, rd, plan, dlv, askVal, owe,
                   looking>>

\* The agent's run completes, or pauses on questions.
Finish(p, outcome) ==
    /\ pc[p] = "running"
    /\ outcome = "paused" => Pauses < MaxPauses
    /\ End(p, outcome) /\ UNCHANGED <<faults, failed>>

\* The run is stopped: by Runner.stop, a closed connection, or its claim, lost.
Stop(p) ==
    /\ pc[p] = "running"
    /\ IF lost[p] THEN UNCHANGED <<faults, failed>> ELSE Fault(TRUE)
    /\ End(p, "stopped")

\* The agent raises.
Fail(p) == pc[p] = "running" /\ Fault(FALSE) /\ End(p, "failed")

-----------------------------------------------------------------------------
\* Failures and cancellations at the other awaits, and crashes.

\* Before a call asks, nothing is handed over: at the log's head, or at the end of the send's own
\* commit, before _take.
Interrupt(p, c) ==
    /\ pc[p] \in {"head", "asking"} /\ Cancellable(p, c) /\ Fault(c)
    /\ Step(p, "idle")
    /\ UNCHANGED <<shared, lease, count, effects, crashes, lapsed, lost, rd, plan, dlv, nxt, snap,
                   askVal, owe, looking>>

\* In _take, from its ask to its claim, a cancellation hands over as it propagates, and so does a
\* failure once _take has read the cursors, with what it read; rd is NoSnap until it has. Both
\* storages run each call to its end and raise a cancellation after it, so the ask is saved if the
\* call reached its write, and not if it was interrupted at the authorization check that
\* Workspace.save_cursor awaits first.
InterruptTaking(p, c, saved) ==
    /\ pc[p] \in {"asking", "reading"} /\ Cancellable(p, c) /\ Fault(c)
    /\ asked' = IF pc[p] = "asking" /\ saved THEN Max(asked, askVal[p]) ELSE asked
    /\ LET read == IF pc[p] = "asking" THEN NoSnap ELSE rd[p]
       IN IF c \/ read # NoSnap
             THEN /\ snap' = [snap EXCEPT ![p] = [read EXCEPT !.c = c]]
                  /\ Step(p, "handing") /\ nxt' = [nxt EXCEPT ![p] = "handover"]
             ELSE Step(p, "idle") /\ UNCHANGED <<snap, nxt, looking>>
    /\ UNCHANGED <<log, taken, runs, lease, count, effects, crashes, lapsed, lost, rd, plan, dlv,
                   askVal, owe, looking>>

\* A claimant fails, or is cancelled, at its claim or holding it: _take hands over as the error
\* propagates, with what it read.
FailClaimant(p, c) ==
    /\ pc[p] \in {"claiming", "abandoning", "planning", "replying"} /\ Cancellable(p, c)
    /\ Fault(c)
    /\ snap' = [snap EXCEPT ![p] = [t |-> rd[p].t, a |-> rd[p].a, c |-> c]]
    /\ IF pc[p] = "claiming" THEN Step(p, "handing") ELSE Step(p, "releasing")
    /\ nxt' = [nxt EXCEPT ![p] = "handover"]
    /\ UNCHANGED <<shared, lease, count, effects, crashes, lapsed, lost, rd, plan, dlv, askVal,
                   owe, looking>>

\* The same at the claim, once the storage granted it: SQL storage runs acquire_lease to its end
\* and raises the cancellation after it. claim_thread releases the claim before it raises, as no
\* other task would, and _take hands over.
ClaimedAsInterrupted(p, c) ==
    /\ pc[p] = "claiming" /\ Acquirable /\ Cancellable(p, c) /\ Fault(c)
    /\ lease' = [owner |-> p, ttl |-> TTL]
    /\ lost' = [lost EXCEPT ![p] = FALSE]
    /\ snap' = [snap EXCEPT ![p] = [t |-> rd[p].t, a |-> rd[p].a, c |-> c]]
    /\ Step(p, "releasing") /\ nxt' = [nxt EXCEPT ![p] = "handover"]
    /\ UNCHANGED <<shared, count, effects, crashes, lapsed, rd, plan, dlv, askVal, owe, looking>>

\* The run's task fails, or is stopped, before run_started is recorded: it consumed nothing, and
\* hands over with what its plan read. Once its claim is lost, it is cancelled.
FailStart(p, c) ==
    /\ pc[p] = "starting"
    /\ IF c /\ lost[p] THEN UNCHANGED <<faults, failed>> ELSE Fault(c)
    /\ snap' = [snap EXCEPT ![p] = [t |-> plan[p].tt, a |-> plan[p].ta, c |-> c]]
    /\ Step(p, "releasing") /\ nxt' = [nxt EXCEPT ![p] = "handover"]
    /\ UNCHANGED <<shared, lease, count, effects, crashes, lapsed, lost, rd, plan, dlv, askVal,
                   owe, looking>>

\* A cancellation at the release: the release takes effect, both storages running it to its end,
\* and the cancellation is raised after it, so the hand-over proceeds.
ReleaseInterrupted(p) ==
    /\ pc[p] = "releasing" /\ (nxt[p] # "handover" => Cancellable(p, TRUE)) /\ Fault(TRUE)
    /\ lease' = IF Mine(p) THEN Free ELSE lease
    /\ snap' = [snap EXCEPT ![p] = IF nxt[p] = "handover"
                                      THEN [@ EXCEPT !.c = TRUE]
                                      ELSE [t |-> rd[p].t, a |-> rd[p].a, c |-> TRUE]]
    /\ Step(p, "handing") /\ nxt' = [nxt EXCEPT ![p] = "handover"]
    /\ UNCHANGED <<shared, count, effects, crashes, lapsed, lost, rd, plan, dlv, askVal, owe,
                   looking>>

\* The process dies: its claim stays in storage until it lapses, nothing is handed over, and its
\* look, and its caller's call, die with it.
Crash(p) ==
    /\ pc[p] # "dead" /\ crashes < MaxCrashes
    /\ crashes' = crashes + 1
    /\ owe' = [owe EXCEPT ![p] = IF @ = "call" THEN "owed" ELSE @]
    /\ looking' = [looking EXCEPT ![p] = FALSE]
    /\ Step(p, "dead")
    /\ UNCHANGED <<shared, lease, count, effects, faults, failed, lapsed, lost, rd, plan, dlv, nxt,
                   snap, askVal, looking>>

\* The process starts again with nothing in memory, and Runner.recover sweeps the thread: it reads
\* the cursors, and takes what was asked and not taken.
Restart(p) ==
    /\ pc[p] = "dead"
    /\ lost' = [lost EXCEPT ![p] = FALSE]
    /\ rd' = [rd EXCEPT ![p] = NoSnap]
    /\ Step(p, "reading")
    /\ UNCHANGED <<shared, lease, audit, plan, dlv, nxt, snap, askVal, owe, looking>>

-----------------------------------------------------------------------------
\* The release, and the hand-over.

\* claim_thread's exit: release the lease, if this claim still has it.
Release(p) ==
    /\ pc[p] = "releasing"
    /\ lease' = IF Mine(p) THEN Free ELSE lease
    /\ Step(p, CASE nxt[p] = "loop" -> "reading" [] nxt[p] = "handover" -> "handing"
                  [] OTHER -> "idle")
    /\ UNCHANGED <<shared, audit, lost, rd, plan, dlv, nxt, snap, askVal, owe, looking>>

\* Runner._take_over: take the next turn if the claimant was cancelled, if a turn took something
\* since it read, or if more was asked since.
HandOver(p) ==
    /\ pc[p] = "handing"
    /\ Step(p, IF snap[p].c \/ taken > snap[p].t \/ asked > snap[p].a THEN "reading" ELSE "idle")
    /\ owe' = [owe EXCEPT ![p] = IF @ = "call" THEN "owed" ELSE @]   \* the call raised
    /\ UNCHANGED <<shared, lease, audit, lost, rd, plan, dlv, nxt, snap, askVal, looking>>

-----------------------------------------------------------------------------
\* The clock, and Workspace._renew. A holder that does not stall renews before its TTL runs out.

Tick ==
    /\ lease # Free /\ lease.ttl > 0
    /\ Stalls \/ ~Live(lease.owner) \/ lease.ttl > 1
    /\ lease' = [lease EXCEPT !.ttl = @ - 1]
    /\ lapsed' = (lapsed \/ (Live(lease.owner) /\ lease.ttl = 1))
    /\ UNCHANGED <<shared, count, effects, crashes, faults, failed, local>>

Renew(p) ==
    /\ Live(p) /\ lease.ttl > 0 /\ lease.ttl < TTL
    /\ lease' = [lease EXCEPT !.ttl = TTL]
    /\ UNCHANGED <<shared, audit, local>>

\* The renewal's timer fires, or a renewal finds another holder: the claim is lost.
Lapse(p) ==
    /\ pc[p] \in Holding /\ ~lost[p] /\ (lease.owner # p \/ lease.ttl = 0)
    /\ lost' = [lost EXCEPT ![p] = TRUE]
    /\ UNCHANGED <<shared, lease, audit, pc, rd, plan, dlv, nxt, snap, askVal, owe, looking>>

\* With nothing more to do, the system stays as it is: no deadlock.
Done == (\A p \in Procs : pc[p] \in {"idle", "dead"}) /\ UNCHANGED vars

Next ==
    \/ \E p \in Procs :
        \/ Send(p) \/ Answer(p) \/ Retry(p) \/ ReadHead(p) \/ SaveAsk(p)
        \/ ReadCursors(p) \/ Acquire(p) \/ Refused(p) \/ LookAgain(p) \/ Abandon(p) \/ Plan(p)
        \/ Reply(p) \/ ReplyFenced(p) \/ RunStart(p) \/ StartRefused(p) \/ StartFenced(p)
        \/ Deliver(p) \/ Finish(p, "completed") \/ Finish(p, "paused") \/ Stop(p) \/ Fail(p)
        \/ \E c \in BOOLEAN : \/ Interrupt(p, c)
                              \/ \E saved \in BOOLEAN : InterruptTaking(p, c, saved)
                              \/ FailClaimant(p, c) \/ ClaimedAsInterrupted(p, c)
                              \/ FailStart(p, c)
        \/ ReleaseInterrupted(p) \/ Crash(p) \/ Restart(p)
        \/ Release(p) \/ HandOver(p) \/ Renew(p) \/ Lapse(p)
    \/ Direct("direct") \/ Direct("notice")
    \/ Tick
    \/ Done

\* What the code does by itself is fair: each step it takes once it may, a run that ends, and a
\* run cancelled once its claim is lost. So is a caller that asks again, when Retries. Sending,
\* answering, pausing, failing, cancelling and crashing are not: they may happen, and never must.
Fairness ==
    /\ \A p \in Procs :
        /\ WF_vars(ReadHead(p)) /\ WF_vars(SaveAsk(p)) /\ WF_vars(ReadCursors(p))
        /\ WF_vars(Acquire(p) \/ Refused(p)) /\ WF_vars(LookAgain(p))
        /\ WF_vars(Abandon(p)) /\ WF_vars(Plan(p))
        /\ WF_vars(Reply(p) \/ ReplyFenced(p))
        /\ WF_vars(RunStart(p) \/ StartRefused(p) \/ StartFenced(p))
        /\ WF_vars(Finish(p, "completed"))
        /\ WF_vars(lost[p] /\ Stop(p)) /\ WF_vars(lost[p] /\ FailStart(p, TRUE))
        /\ WF_vars(Release(p)) /\ WF_vars(HandOver(p)) /\ WF_vars(Restart(p))
        /\ WF_vars(Lapse(p)) /\ WF_vars(Retry(p))
    /\ WF_vars(Tick)

Spec == Init /\ [][Next]_vars /\ Fairness

-----------------------------------------------------------------------------
\* A run starts with a message as its prompt; once claims lapse, each process may start one.
MaxRuns == MaxLog * Cardinality(Procs)

TypeOK ==
    /\ log \in Seq({"sent", "direct", "notice", "answer"}) /\ Len(log) <= MaxSeq
    /\ asked \in 0..MaxSeq /\ taken \in 0..MaxSeq
    /\ runs \in Seq([st : {"running", "paused", "completed", "failed", "stopped"},
                     open : 0..MaxReq, pause : 0..MaxPauses])
    /\ Len(runs) <= MaxRuns
    /\ plan \in [Procs -> [kind : {"none", "new", "reply", "resume"}, run : 0..MaxRuns,
                           lo : 0..MaxSeq, hi : 0..MaxSeq, msg : 0..MaxSeq, pause : 0..MaxPauses,
                           tt : 0..MaxSeq, ta : 0..MaxSeq, done : BOOLEAN]]
    /\ lease.owner \in Procs \cup {"none"} /\ lease.ttl \in 0..TTL
    /\ pc \in [Procs -> Holding \cup {"idle", "head", "asking", "reading", "claiming", "handing",
                                      "dead"}]
    /\ owe \in [Procs -> {"no", "call", "owed"}] /\ looking \in [Procs -> BOOLEAN]

\* I1. A message is recorded as consumed at most once: by the one write that consumes it.
I1_ConsumedAtMostOnce == \A i \in DOMAIN count : count[i] <= 1

\* I1. The taken cursor never passes a message that no write consumed.
I1_NoneSkipped == \A i \in 1..taken : Msg(i) => count[i] >= 1

\* I1, as a model is given each message: once, unless a claim lapsed while its holder lived
\* (ADR-0055's one exception), or a process died, whose run's steering is given again.
I1_GivenOnce == (crashes = 0 /\ ~lapsed) => \A i \in DOMAIN effects : effects[i] <= 1

\* I2. The cursor moves only with a write that consumes: a run's start, an answer, a run's end;
\* or, as runner.py does in a write of its own, a plan that finds no message to carry out.
I2_ConsumedWithItsWrite ==
    [][taken' > taken =>
        \E p \in Procs : \/ RunStart(p) \/ Reply(p) \/ Plan(p)
                         \/ Finish(p, "completed") \/ Finish(p, "paused")
                         \/ Stop(p) \/ Fail(p)]_vars

\* I3. A claim in storage that has not lapsed is held by a task that will release it, while no
\* process has died.
I3_ClaimHasATask ==
    (crashes = 0 /\ lease # Free /\ lease.ttl > 0) => pc[lease.owner] \in Holding

\* I3. What is asked and not taken is left to a task that will look at it, while nothing has
\* crashed or failed: one that holds the claim, or will ask, claim or hand over.
I3_NoStrandedAsk ==
    (crashes = 0 /\ ~failed /\ asked > taken) =>
        \E p \in Procs : pc[p] \in Holding \cup {"head", "asking", "reading", "claiming", "handing"}

\* I3. One run is active in a thread: its holder's.
I3_OneActiveRun == Cardinality({r \in DOMAIN runs : runs[r].st \in {"running", "paused"}}) <= 1

\* I4. A turn that fails or is stopped before it starts consumes nothing.
I4_NothingTakenUnstarted ==
    [][\A p \in Procs : \A c \in BOOLEAN :
          (FailStart(p, c) \/ StartRefused(p) \/ StartFenced(p) \/ ReplyFenced(p)
              \/ FailClaimant(p, c))
              => UNCHANGED <<taken, count>>]_vars

\* I5. A message committed directly, or a notice, asks for nothing and starts nothing.
I5_DirectAsksNothing ==
    [][(Direct("direct") \/ Direct("notice")) => UNCHANGED <<asked, runs, lease, pc>>]_vars

\* I6. The reply is the oldest message not consumed, however it was committed.
I6_OldestIsTheReply ==
    [][\A p \in Procs :
          (Reply(p) /\ ~plan[p].done /\ plan'[p].done) =>
              /\ Msg(plan[p].msg)
              /\ \A i \in 1..plan[p].msg - 1 : Msg(i) => count[i] >= 1]_vars

\* Witnesses, none a property of the protocol: each is violated once TLC reaches what it names,
\* which shows the behaviours the properties above are checked over are there. README.md records
\* the runs.
NeverPaused == \A r \in DOMAIN runs : runs[r].st # "paused"
NeverReplied == \A p \in Procs : ~plan[p].done
NeverResumed == \A r \in DOMAIN runs : runs[r].pause = 0 \/ runs[r].st # "running"
NeverRefused == \A p \in Procs : ~(pc[p] = "claiming" /\ ~Acquirable)
NeverHandedOver ==
    \A p \in Procs : ~(pc[p] = "handing" /\ (snap[p].c \/ taken > snap[p].t \/ asked > snap[p].a))
NeverSteered == \A p \in Procs : ~(pc[p] = "running" /\ dlv[p] > plan[p].hi /\ Msg(dlv[p]))
NeverFenced == \A p \in Procs : ~(pc[p] = "starting" /\ lease.owner # p)

\* Every message asked for is taken, while nothing fails: cancellations and crashes may happen.
AskedIsTaken ==
    [](~failed) =>
        \A i \in 1..MaxSeq : (Msg(i) /\ asked >= i) ~> (count[i] >= 1)

\* Every message sent with the runner is taken, while nothing fails.
SentIsTaken ==
    [](~failed) =>
        \A i \in 1..MaxSeq : (i <= Len(log) /\ log[i] = "sent") ~> (count[i] >= 1)
=============================================================================
