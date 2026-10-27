# ADR-0097: A message chooses the model of the turn it starts

**Status:** Accepted
**Date:** 2026-10-27
**Deciders:** Alex Nodeland
**Amends:** [ADR-0055](0055-turns-from-the-log.md), whose turns gain a model; [ADR-0095](0095-a-run-that-waits-on-nothing-is-failed-and-a-message-that-starts-nothing-is-told.md), whose notice style a model not used follows

## Context

A Runner answers every turn with its agent's one model. The owner asked to choose the model per message, from the composer: pre-selected per thread with the thread's last model, which the client remembers; and, if the gateway falls back to another model during a run, to be told which model actually answered, never silently. Which models are offered, and the composer's picker, come later (the streaming design's phase D2); this record is the core, the runner and the access they need.

pydantic-ai 2.55's `Agent.run` takes `model=`, a `Model` or a name, which replaces the agent's own for that run (verified in the installed source); an `Agent.override(model=...)` still wins over it. Each step's `StepUsage.model` already names the model that answered ([ADR-0096](0096-a-run-counts-each-model-request-exactly-live-and-at-its-end.md)).

## Decision

- **On the wire, three optional fields.** `post_message.model` names the model to answer with, by the host's name for it; `message_posted.model` records what was asked; `run_started.model` records what the attempt asked for, `null` for the agent's own. Each defaults to `null`, so old logs and clients still validate, and the protocol stays `artifactr.v1`. A notice starts no turn, so `post_message` refuses a `model` with `kind: "notice"`, and an empty name.
- **The host names its models.** `Runner(model_for=...)` is a function from a name to a pydantic-ai `Model` that raises `LookupError` for a name it doesn't know, as a dict's `__getitem__` does. The runner calls it as each turn starts, so the host builds each model once. Without it, every turn answers with the agent's model, as before.
- **A turn answers with the model of its first message.** The turn's watcher delivers later messages into the running turn, which keeps its model: a model applies when its message starts a new turn, as the composer will say. A resumed run answers with its reply's model, or, with none, the one the run last asked for, which `Run.model` keeps from `run_started` (the run's stored body is JSON, so no migration).
- **Who may choose: `artifactr:use_model`.** The turn asks it as its agent acting for its author, as it asks `artifactr:record` to start ([ADR-0057](0057-a-turn-acts-for-one-author.md)), with the model's name in a new `Access.model`. grantr's `editor`, and every role above it, holds it, for every model: a model is no item of a workspace, so grantr scopes the ask by the thread, as it scopes every artifactr action. Which models a tenant is offered is narrowed where the host lists them, by the gateway and a tenant's settings (phase D2); an `authorize` of the application's own may read `Access.model` to refuse one.
- **A model not used is never silent.** A model its author may not use, one the host doesn't know, or any model where the runner has no `model_for`, is not refused to the sender: the turn answers with the agent's own model, `run_started.model` is `null`, and the runner posts a notice, after [ADR-0095](0095-a-run-that-waits-on-nothing-is-failed-and-a-message-that-starts-nothing-is-told.md)'s and [ADR-0070](0070-a-runner-looks-again-for-what-a-dead-holder-was-asked.md)'s rule: what was asked, what is answering instead, and what to do, in people's words. The check is made holding the thread, as the turn is planned, so a message that only joins a running turn asks nothing.
- **The model asked for, and the model that answered.** `run_started.model` is the request, as accepted; each step's `StepUsage.model`, live in the `usage` frame and recorded in `run_ended`, is the model whose response it was. A client shows the step's, so a gateway's fallback shows as another model's name rather than passing unseen.

## Options considered

### Option A: The first message chooses, a refusal falls back with a notice (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one field on the turn, one check as it is planned |
| Predictability | A running turn never changes model mid-way; the next turn chooses again |
| Failure | Never silent and never a lost message: a refusal answers with the default, and says so |

### Option B: Refuse the message whose model is not allowed

Rejected: a refusal at send time misses a message committed another way, which the next turn still takes, and a refusal as the turn starts would leave the message unanswered. The owner asked for an answer that says which model gave it.

### Option C: Each message, joining or not, switches the running turn's model

Rejected: pydantic-ai runs a turn with one model; switching would stop and restart the run, and the cache a turn warms would go with it.

## Consequences

**Positive:**

- A person picks a model per message, and the thread's log says which was asked for and which answered.
- Hosts that pass no `model_for` are unchanged, stackr's template among them.

**Negative:**

- A turn checks one more action when its message names a model; a message that names none checks nothing more.
- The notice of a model not used is posted as the turn starts, so an agent whose capability asks for notices ([ADR-0051](0051-notices.md)) is told it too.
- grantr grants every model or none: narrowing to some models is the host's listing and settings, not a role.

**Risks:**

- A host whose `model_for` raises something other than `LookupError` fails the turn, as any failure of the model would; the guide says to raise `LookupError`.

## Action items

1. [x] `PostMessage.model`, `MessagePosted.model`, `RunStarted.model`, `Run.model` and `Access.model`; the schemas and the client's types regenerated
2. [x] `Runner(model_for=...)`, the turn's model, `artifactr:use_model` in artifactr's catalog and grantr's `editor`, and the notices
3. [ ] The host's listing of the models a tenant may use, the composer's picker and stackr's factory (the streaming design's phase D2)
