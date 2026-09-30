# ADR-0045: A message id is used once in a workspace

**Status:** Accepted
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

## Context

`PostMessage` carries a `message_id`, but core never checked it, so a repeated post appended a second message and, through the runner, started or steered a second turn ([#61](https://github.com/alexnodeland/artifactr/issues/61)). The runner's memory of `command_id`s ([ADR-0022](0022-surfaces-over-one-command-handler.md)) lives in one process and forgets. [stackr RFC-0002](https://github.com/alexnodeland/stackr/blob/main/docs/rfcs/0002-the-combined-system.md) posts messages from reflexr runs, which retry, and counts `invalid_state` on a create with its own id as done. Messages are not entities ([ADR-0037](0037-feedback-targets-and-evaluators.md)), so core had nothing to check an id against without reading the log. Every other command a client may retry is already refused durably or repeats as a no-op, except `give_feedback`, which has no id and which RFC-0002 doesn't need.

## Decision

- **A used message id is refused with `InvalidState`** ("message m1 already exists"), in any thread of the workspace, as duplicate artifact, proposal and thread ids are. Nothing is appended, and `Runner.send` raises before it acts, so no second turn starts.
- **Core decides, through the `needs` loop** ([ADR-0018](0018-core-host-contract.md)). `needs(PostMessage)` asks for the message id; the host loads `State.messages`, whether each id is used; and `CommitResult.messages` lists the ids to record as used.
- **Storage keeps only the ids.** `InMemoryStorage` keeps a set per workspace. SQL storage keeps a table, `artifactr_messages`, keyed by tenant, workspace and id; migration 0003 fills it from the stored `message_posted` events.

## Options considered

| Option | Trade-off |
|---|---|
| **Refuse, with ids loaded through `needs` (chosen)** | Like every other create; the rule stays in core and its fixtures, and a check is one key lookup |
| Return the existing message | Unlike every other create. The runner would need an "already posted" flag not to start a second turn, and a different message with a reused id would be dropped silently |
| Look the id up in the workspace, outside core | A rule outside core and its fixtures |
| A unique constraint in SQL alone | In-memory storage would differ, and PostgreSQL aborts the transaction on the violation |
| Scan the thread's events for the id | The cost grows with the thread |

## Consequences

- Easier: a caller that chooses its message ids posts each message once, across retries, processes and restarts.
- Harder: a `Storage` implemented elsewhere must load `Needs.messages` and save `CommitResult.messages`; one that doesn't fails with `NotLoaded` on the first post.
- If a process dies between posting a message and starting its turn, a retry is refused and the turn never runs ([#68](https://github.com/alexnodeland/artifactr/issues/68)).
