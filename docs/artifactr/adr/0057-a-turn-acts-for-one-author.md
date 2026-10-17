# ADR-0057: A turn acts for one author

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

With access asked in every workspace method ([ADR-0056](0056-access-asked-in-every-workspace-method.md)), the agent's writes are checked as its actor, `AgentActor`, which said nothing about whom it worked for. The person whose message started a run was only `Session.requested_by`, which spans and the gateway read, and no check saw.

The `Runner` also took every message not yet taken into one turn ([ADR-0055](0055-turns-from-the-log.md)): the first as the prompt, the rest through the run's watcher, or all of them beside a resumed run's answers. Once a turn is checked as the person it acts for, that would let one person's message ride on another's rights: a viewer's message steering an editor's run.

[lattice RFC-0001](../../rfcs/0001-grantr-identity-and-access.md) decides that a turn acts for the user whose message started it (D4). In the work codebase lattice grew beside, one agent tool checked a thread's owner instead of the user acting, so a viewer inherited the owner's writes.

## Decision

- **`AgentActor.on_behalf_of: UserActor | ExternalAgentActor | None`** is whom a run acts for: the author of the message or answer that started its segment, when that is a person or a person's MCP client. It replaces `Session.requested_by`; `Session.on_behalf_of` reads it from the session's agent. The system, an evaluator or another agent acts for no one, so a run they start has none, and is checked as the agent alone.
- **`ExternalAgentActor.on_behalf_of: UserActor | None`** is the person an MCP client acts for: set when a person connects with their own token, as the template's resolver now does, and left empty for a client with credentials of its own.
- **The log says whom each agent write was for.** Every envelope records its actor, so the run's `run_started`, and each write after it, carries `on_behalf_of`. The protocol's actor gains the field, `null` when there is none.
- **The agent's `participant` is unchanged,** `agent:{thread_id}`, so command de-duplication, change notes and "the agent's own changes" are as before.
- **A turn takes messages only up to the first change of author.** Authors are compared by whom they act for (`same_principal`): a person and their client are different authors, and everything that acts for no one is one.
  - A run's watcher stops at the first message from another author, before marking it delivered, so the message stays untaken and the run's hand-over starts the next turn with it ([ADR-0055](0055-turns-from-the-log.md)'s I1 and I2 hold).
  - A resumed run acts for whoever answered it last. The messages not taken join its prompt only up to the first from another author; it takes the log up to just before that message, which starts the next turn.
  - A paused run's reply acts for whoever wrote it, as before.
  - A resume with no answer in the log to act for (a resume that failed before it began took them) acts for the author of the oldest message not taken, or, with none, for no one.
- **A turn its author may not start is passed over, so it can't wedge its thread.** Starting a turn records its `run_started` as the agent acting for the author, so `authorize` hears `artifactr:record` for them. `Runner.send` asks it before it posts, so a sender who may not start a turn is refused and nothing is posted. A message committed otherwise, or a reply its author may not give (`artifactr:answer_deferred`), would otherwise be refused at every turn after it. The runner, as the system, takes the log past such a message, records nothing for it, and plans the next turn; a paused run whose resume is refused is recorded as failed, with the reason `forbidden`. Each refusal takes more of the log, or ends the run, so planning ends. A new run closes the tool calls an ended run left open in the thread's history, with pydantic-ai's `repair_messages`, so a run that ended while paused, or failed after resuming, doesn't stop the next one.
- **The proposal check looks through `on_behalf_of`.** A responder who is the proposal's author, or acts for them through an agent's run or an MCP client, cannot accept or reject it (`acts_as`). A person's own MCP client is the person both ways, so neither resolves what the other proposed. A thread's agent is the one exception: a person can still accept what a run for them proposed, which is how suggest mode works.

## Options considered

### Option A: the person on the actor, and one author per turn (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one field, a stop in the watcher, a cut in the resume |
| Safety | A check sees exactly who acts and for whom |
| Turns | A thread where two people talk at once makes more turns |

### Option B: the agent's own grants, whoever is chatting

Rejected by the RFC (D4): the agent would hold the union of what anyone may ask of it.

### Option C: keep batching, and check the run as the least privileged author

| Dimension | Assessment |
|---|---|
| Complexity | High: a turn's rights change as messages arrive |
| Safety | A run's earlier writes were checked against rights it no longer has |

## Trade-off analysis

One author per turn costs turns when people talk over each other in one thread, and the model sees two people's messages in two turns rather than one. It makes the actor of every check the one acting, which the work codebase's bug shows is the property that matters. Comparing by whom actors act for keeps the system's notices and an application's automated messages in one turn, since none of them carries rights of a person.

## Consequences

- Easier: grantr checks an agent's write as the person it acts for, capped by the agent's write policy.
- Easier: the log says whom each agent write was for.
- Harder: a message from someone else no longer steers a running turn; it waits for the next one. The watcher stops there, so others' changes made after that message reach the run no more either; the next turn's watcher delivers them.
- Harder: `Session.requested_by` is gone; read `Session.on_behalf_of`. Spans, the gateway and Langfuse record a person there, as before.
- Revisit: a turn's visibility, when phase 5 of the RFC filters what the agent's tools read by the person it acts for.

## Action items

1. [x] `on_behalf_of` on `AgentActor` and `ExternalAgentActor`, set by the `Runner` and the template.
2. [x] One author per turn, in the watcher and the resume.
3. [x] The proposal check through `on_behalf_of`.
