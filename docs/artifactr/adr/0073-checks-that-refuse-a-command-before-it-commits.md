# ADR-0073: Checks that refuse a command before it commits

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland
**Amends:** [ADR-0010](0010-pausing-with-deferred-tools.md)

## Context

[lattice RFC-0005](../../rfcs/0005-forms-dashboards-and-mini-apps.md) puts forms in the chat, in `artifactr.ui` behind the `forms` extra ([ADR-0074](0074-forms-and-dashboards-in-artifactr-ui-behind-the-forms-extra.md)), a layer nothing else in artifactr imports. A form is answered two ways: an `answer_deferred` to a paused run's `ask_form`, or a `create_artifact` of a `submission`. Both must be refused when the values don't fit the form's schema, the form is closed, or the submission was made against an older version of it, and the refusal must reach the person, under the field it is about.

Nothing in artifactr can refuse them:

- **Core records an answer as given.** `_answer` checks that the run is paused, that the request exists and is unanswered, and that its kind matches; nothing about the answer itself.
- **Core may not import a schema validator,** nor know of forms: they are `artifactr.ui`'s types, a layer core never imports ([ADR-0003](0003-artifact-types-as-pydantic-subclasses.md)).
- **`authorize` decides who, not what.** It hears an `Access`, the action and the thread or artifact it names, never the command's values ([ADR-0056](0056-access-asked-in-every-workspace-method.md)), and it answers with a boolean, so it can't say which field was wrong.

The RFC recommends one additive hook on `Workspaces`, which `artifactr.ui` fills (its U1), and the maintainer chose it.

## Decision

- **`Workspaces(checks=...)`** takes a mapping from a command's `type` to a `Check`, and `Check = Callable[[Workspace, Command], Awaitable[None]]`. `Check` is exported from `artifactr.workspace` and `artifactr`. Without checks, nothing changes.
- **A check runs in `Workspace.commit`,** after `authorize` allows the command and core's own checks of what it names pass (the target's access and the type allowlist), and before its transaction. A command refused before it is never checked, so a check never hears a command from an actor who may not send it.
- **A check is given the committing handle,** so it reads the workspace as the command's actor, `workspace.actor`, through the same `authorize` and `hidden` as any read: a submitter who may not read the form is refused as one who may not see it. The RFC wrote the check as `(workspace, actor, command)`; a handle already carries its actor, so the actor is not passed twice.
- **A check refuses with a `Rejection`,** usually `ValidationFailed`, whose `errors` name the fields as Pydantic does, or `InvalidState`. A refusal is counted and traced as a rejection, as core's are, and reaches the client typed: a `validation_failed` result over the WebSocket, 422 over REST. Anything else a check raises fails the command as an error, as the rest of the write path's errors do.
- **A command is checked under its own type.** A `propose_change` is checked under `"propose_change"`, whatever change it wraps, and the change is not checked again under its own type. A check of `create_artifact` that matters for proposals too is registered under both. Accepting a proposal is a `respond_to_proposal`, checked under that type, and core then applies the proposed change, rebased onto the head, with the reviewer's own `changes` on top: a check that must hold when a change lands, not only when it is proposed, is registered under `"respond_to_proposal"` too, reads the proposal, and checks the change against what is current. `artifactr.ui`'s checks do ([ADR-0075](0075-forms-refused-at-the-boundary-through-the-checks.md)).
- **Facts are not checked.** `Workspace.record` is the runner's and the capability's, recording what a run did, not what a person asks; a check is for commands.
- **A check is not a lock.** It reads before the transaction and holds nothing, so what it read may change before the command commits: a form closed between the check and the commit takes one late submission. Whoever needs more puts the invariant in core's rules, or reads the result with it in mind.

## Options considered

### Option A: a check hook on `Workspaces`, by command type (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one lookup and one call in `commit` |
| Coverage | Every surface and in-process call, as `authorize` |
| Core | Unchanged; no validator, no knowledge of forms |

**Pros:** additive; the code that owns a type owns its checks; a refusal is a typed rejection with field errors.
**Cons:** a check runs outside the transaction, so it is not a lock.

### Option B: a `submit` command in core

| Dimension | Assessment |
|---|---|
| Complexity | High: a command, its rule and a schema validator in core |
| Coverage | As A |
| Core | A release of core for every change to forms |

**Pros:** the check could run inside the transaction.
**Cons:** core would import a validator and know of forms, which [ADR-0001](0001-python-library-with-sans-io-core.md) and the RFC's non-goals rule out.

### Option C: record anything, and leave every consumer to check

| Dimension | Assessment |
|---|---|
| Complexity | Low in artifactr, high everywhere else |
| Coverage | Whatever each consumer remembers |

**Pros:** nothing changes here.
**Cons:** the log keeps values no form accepts; the resumed turn, every rule and every renderer re-checks them, and a person learns of the mistake late, or never.

### Option D: a richer `authorize`

Rejected: it would hear every command's values, and answer with errors rather than a boolean, for forms' need alone; and an application's access rules, grantr's among them, would have to pass values through.

## Trade-off analysis

A hook by command type costs a dictionary lookup per commit and keeps core as it is. Running it before the transaction, rather than in it, keeps storage's transactions short and free of the application's reads, at the price of the late submission the RFC already accepts. Passing the committing handle, rather than the actor and a handle of the application's choosing, means a check can only read what the actor could, so it can't become a way around `hidden`.

## Consequences

- Easier: an application's checks, and `artifactr.ui`'s, refuse what doesn't fit their types, at the boundary, with errors a client can show under each field.
- Easier: one hook covers the REST surface, the WebSocket, MCP, the agent's tools and in-process calls alike.
- Harder: a check of `answer_deferred` hears the runner's replies too, a chat message answering a paused run's questions. One that refuses them with `InvalidState` leaves the question open, as an answer that came first does; any other refusal fails the turn's planning. artifactr's runner never replies to a form ([ADR-0055](0055-turns-from-the-log.md)'s amendment), so `artifactr.ui`'s checks don't meet it.
- Harder: a check that reads costs a read per command of its type.
- Revisit: a check inside the transaction, if a late submission is ever more than a nuisance.

## Action items

1. [x] `Workspaces(checks=...)` and `Check`, with tests on every storage: a refusal, an error, a read as the actor, `propose_change` under its own type, and facts unchecked.
2. [x] `artifactr.ui`'s `ui_checks()` fills it (lattice RFC-0005, phase 1).
