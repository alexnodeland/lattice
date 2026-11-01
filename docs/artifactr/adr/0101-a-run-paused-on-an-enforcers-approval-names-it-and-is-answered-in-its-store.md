# ADR-0101: A run paused on an enforcer's approval names it, and is answered in its store

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** lattice [RFC-0011](../../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md)'s "deferred approvals backed by `Approval`", the follow-up [ADR-0099](0099-artifactrs-tools-as-capabilities-called-through-the-enforcer-whose-policy-asks-approval.md) leaves; on lattice [ADR-0037](../../adr/0037-the-enforcement-path-in-lattice-core-refusals-by-step-approvals-resumed-by-id.md)

## Context

lattice's enforcer asks an approval at its step 6 and stores it in the application's `Approvals`, grantr's store in lattice's applications. Through lattice-core's agents bridge, the call raises pydantic-ai's `ApprovalRequired` with the approval's id in its metadata, under `approval`, so artifactr's runner pauses the run as it does for its own approvals. When the run resumes approved, the bridge calls the enforcer again with that id. The enforcer lets the call through only if the store holds the approval answered yes, for this call (ADR-0037).

Three things were missing for artifactr's runs:

- **The runner dropped the metadata.** A `DeferredRequest` kept the call's arguments and its review, not the approval's id. A run resumed approved called the enforcer with no id, which asked a new approval and paused again, and kept doing so.
- **An answer in the thread wasn't the store's.** `answer_deferred` only recorded the answer in artifactr's log. The approval stayed pending in grantr, where portalr's approvals list showed it, and the enforcer then refused the call.
- **An answer given anywhere else didn't reach the run.** RFC-0011 says "a run paused on one approval resumes whichever surface answered": portalr's approval page (portalr ADR-0093), its confirm page, the expiry sweep, or a withdrawal. Nothing in artifactr heard any of them.

## Decision

- **A request names its approval.** `DeferredRequest.approval` is the id of the approval the call waits on, read from the call's metadata under lattice-core's `APPROVAL` key. It is `None` for questions and for approvals artifactr's own tools ask, such as a connected app's code (ADR-0085). A surface can link the request to the approval's page by it.
- **Resuming gives the id back.** The runner's `DeferredToolResults` carries `{approval: <id>}` as each such call's metadata. So the bridge calls the enforcer with the id, and the call goes ahead on that approval alone. It isn't asked again, and is taken once.
- **An answer sent with the Runner is the store's.** `Runner(approvals=..., surface="portalr")` takes the application's store, the one its enforcer asks. Only a person answers one: an outside client, an agent or the system is `Forbidden`, as RFC-0014 keeps answers to people. A Runner with no store refuses an answer to one, since its answer would count nowhere. `Runner.answer` on a request that names an approval does the following, in order:

  1. It asks artifactr's own `artifactr:answer_deferred`, as for any answer, before the store hears anything.
  2. It answers the store as the person the handle's actor is, `Subject(id=<user id>)`, on `surface`. The answer carries the digest of the arguments the request shows, and the answer's text, if any, as the reason. The store says who may answer: its `answerers`, its first-answer-wins and its deadline.
  3. It commits the answer in the thread.

  The store's refusal is the answer's:

  - one who may not answer (`NotAnAnswerer`) is `Forbidden`;
  - an approval the store doesn't hold is `NotFound`;
  - an answer to other arguments is `InvalidState`;
  - one settled already, as answered first on another surface, expired or withdrawn (`NotPending`), is `InvalidState` with the store's words. The thread takes the settlement, as below.
- **The Runner follows each approval a paused run waits on,** through the store's `watch`, until the store settles it. It starts when a run of this process pauses, as the run hands its thread over, and for every paused run when `recover` starts the application. Then it commits the settlement in the thread as `answer_deferred` and resumes the run:
  - The answer is approved only if the approval was. Its text is the answer's reason, or, for one that closed unanswered, its state and why, such as `expired: past its deadline unanswered`. The model is told that text, as a denial's.
  - **It is committed as the person who answered,** so the run resumes for them, as if they had answered in the thread (ADR-0057). One that expired or was withdrawn, or that a service principal answered, is committed as the person it was asked for. One the thread's `authorize` refuses that person, or asked for no one, is committed as the Runner.
  - One the thread has an answer for already is left as it is: the first to reach the thread stands, and both carry the store's one answer.
- **A message doesn't answer one.** A message in a paused thread answers its questions and declines artifactr's own approvals, as before. It leaves an enforcer's approval open, as it leaves a form: its author may not be one who may answer it, and the store decides that. The message waits, untaken, and reaches the run as it resumes.

## Options considered

### Option A: Follow the store from the Runner (chosen)

**Pros:** artifactr alone carries it out, through the store's own contract (`watch`), whatever answered: a page, a push, the sweep. A paused run is followed again from the log as the application starts, so nothing is lost when a process dies.
**Cons:** grantr's `watch` reads an approval once a second while it waits, in each process that follows it, so a deployment with many paused runs reads many times a second.

### Option B: The store tells its surfaces (`ApprovalSurface.resolved`)

**Pros:** a push, not a poll.
**Cons:** grantr's store tells no surface yet, and in a stack where artifactr runs in another service than grantr's store, the push would need a transport (relayr) that carries grantr's events, which none does.

### Option C: A message declines an enforcer's approval, as it does artifactr's own

**Pros:** what a message did before.
**Cons:** declining is the store's answer, which only its answerers may give. A message from someone else would either be refused, wedging the thread, or withdraw the approval, which lets anyone in the thread cancel what a different approver was asked.

## Consequences

- Easier: an application can offer its capabilities to artifactr's agent through lattice's bridge. A call it defers is answered in the thread, on portalr's approvals page or confirm page, or not at all, and the run resumes either way.
- Easier: what grantr's store records is what happened. The thread's answer is the store's, by the same person, on the page it was given on.
- Harder: an application builds its Runner with the store its enforcer asks. A Runner without one refuses an answer to an enforcer's approval.
- Harder: a paused run's approval is read once a second by each process following it. A push from the store can replace the poll (Option B).
- Harder: in the thread, an approval that expired or was withdrawn reads as declined by the person it was asked for, with why.
- Follow-ups:
  - portalr's thread card linking a request that names an approval to its page, and saying who may answer it;
  - withdrawing an approval when its run is stopped or abandoned (RFC-0011);
  - artifactr's own thread agent's tools through the bridge (ADR-0099).
