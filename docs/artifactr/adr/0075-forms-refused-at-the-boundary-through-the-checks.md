# ADR-0075: Forms refused at the boundary, through the checks

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

## Context

artifactr records an answer or a new artifact as given, and core may not import a schema validator. [lattice RFC-0005](../../rfcs/0005-forms-dashboards-and-mini-apps.md)'s U1 recommended a check hook on `Workspaces`, which forms fill; [ADR-0073](0073-checks-that-refuse-a-command-before-it-commits.md) added it as `Check = (workspace, command)`, the committing handle carrying its actor, each command checked under its own type. artifactr can't import grantr, so it can't ask who is a workspace's admin. A submission's policy (once, one a person, many) has to hold under retries and races, and a change must hold when it lands, not only when it is proposed: accepting a proposal is a command of its own, and core applies the proposed change rebased onto the head, with the reviewer's `changes` on top.

## Decision

- **`artifactr.ui.ui_checks(is_admin=None)` returns a check per command type** for `Workspaces(checks=...)`: `answer_deferred`, `create_artifact`, `edit_artifact`, `archive_artifact`, `propose_change` and `respond_to_proposal`. Each reads the workspace as the command's actor, and is typed against its own command.
- **An answer to `ask_form` is checked against the schema in its request's `args`;** `args` the subset doesn't hold, from a tool of the same name that didn't check them, are refused as `ValidationFailed`. An answer to any other tool, to no request, or a second answer is left to artifactr, so its refusal (`NotFound`, `InvalidState`) is the one a client sees.
- **A submission is checked in the RFC's order:** its form exists and the submitter may read it (`NotFound`); it isn't closed or archived (`FormClosed`), and the version it names is the head's (`FormChanged`); its values fit (`ValidationFailed`, each error at its property); a `many` form's carries its nonce and the others' none; its id is its derivation (`ValidationFailed` at `artifact_id`). A submission to an app is checked the same way, without a schema.
- **The two `InvalidState` refusals say why.** `FormChanged` and `FormClosed` keep the code `invalid_state` and add `reason`, `"changed"` or `"closed"`, with the target's `artifact_id` (and, for a change, the `version` named and the `head`) to their payload, which every surface sends as it is, through `Rejection.payload()`; the wire schema names the reasons (`refusal_reason`). An `invalid_state` without one, to an answer, is artifactr's: the request was answered already.
- **A submission's id is derived** by `submission_id`: `sub_` and 32 hex digits of SHA-256 over the parts joined by NUL, which no id holds: the policy and the form's id, `["once", form_id]`, `["per_person", form_id, acting_for(actor).participant]` or `["many", form_id, nonce]` (and an app's as `many`). artifactr refuses an id in use, so a retried submit is one artifact and the policy holds without a lock ([ADR-0045](0045-a-message-id-is-used-once.md)'s pattern, and [relayr ADR-0019](../../relayr/adr/0019-runs-act-once-through-derived-ids-and-keyed-edits.md)'s). The policy is a part, so a form whose policy changes takes submissions afresh, and a nonce never passes for a principal. A `per_person` submission from whoever acts for no one, the system or an evaluator, is `Forbidden`. Committed vectors, `tests/ui/vectors/submission_ids.json`, are read by portalr's tests too.
- **A submission is a person's alone.** No one edits one, a person, an admin or an agent alike; it is never proposed; it is archived only by its author or whom `is_admin` allows.
- **A form's `schema`, `submissions` and `closed` change only by its author or whom `is_admin` allows, and so does its archiving.** The author is read from its first revision, and is the same participant, or one acting for the same person or client: the person whose agent's run made a form may close it, and every run made for them. A run that acts for no one is its own author alone. `is_admin` is `Callable[[Workspace], Awaitable[bool]]`, the application's, since only it knows grantr's roles; without it only the author may.
- **An app is an agent's.** Only an agent makes one, and a person changes its `state` alone.
- **A proposed change is checked as the change itself when it is proposed, and again when it is accepted,** as its proposer, against the head it will land on; a reviewer's own `changes` aren't taken on a form, an app or a submission, which are accepted or rejected as proposed.
- **A submission's thread needn't be its form's.** A form artifact records no thread, so a check could find it only in the log; a submission carries the thread it was sent in, which relayr's `ui:form_submitted` names.
- **A stale edit is left to artifactr** as a version conflict: a direct edit is checked against the head only when based on it; an accepted one, always.

## Options considered

| Option | For | Against |
|---|---|---|
| **The hook, filled by `artifactr.ui` (chosen, U1)** | Core stays free of a validator and of forms; additive | A check reads before it commits, and holds nothing |
| A core `submit` command | One atomic decision | A validator in core, and a core command for one layer's types |
| Record anything; every consumer re-checks | Nothing new in artifactr | Every reader of the log repeats the check, and a bad value is in the log for ever |
| **`is_admin` from the application (chosen)** | No dependency on grantr; any application's notion of an admin | The application writes one function |
| **Reasons in the payload (chosen)** | A client tells "changed" from "closed" without reading prose | Two subclasses of `InvalidState` |
| A code of their own | As plain | A code artifactr's surfaces and their documents don't list |

## Consequences

- Easier: a bad answer or submission never reaches the log, and portalr shows each refusal under its field, and "This form changed" or "Closed" from its reason.
- Harder: a check is not a lock. A form closed between the check and the commit takes one late submission; whoever reads submissions keeps the form's `closed` in mind.
- Harder: an application with checks of its own for the same command types combines them in one.
