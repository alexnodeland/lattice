# ADR-0032: Runs in admin, with Retry, Skip and Cancel

**Status:** Accepted
**Date:** 2026-10-15
**Deciders:** Alex Nodeland
**Amends:** [RFC-0002](../../rfcs/0002-portalr-the-portal.md), whose admin Runs row is read-only: "Failed and dead-lettered runs in the workspace the admin picks, until a library offers a tenant-wide read" (the table is edited to match)

## Context

lattice RFC-0002 gives the app Runs with retry, skip and cancel where allowed ([ADR-0018](0018-the-runs-area-and-feedback.md)), and admin a read-only list of failed and dead-lettered runs in a workspace the admin picks. This is the last part of admin's Traces and logs area (6d-iii): the Runs area, with the actions.

What the libraries do:

- A reflexr run is the durable record of one firing's action. Its states are `pending`, `running`, `retrying`, `succeeded`, `dead`, `cancelled` and `skipped`. The REST read says `dead`; the stream's `reflexr:run_dead_lettered` event is what `client`'s store shows as `dead_lettered`, and admin reads the stream alone, so it says dead-lettered.
- A **dead-lettered run** is a rule's run that failed every attempt (a rule's `max_attempts`, five by default, with exponential backoff). For a rule ordered by scope with `on_dead_letter="block"`, it also holds back the later runs of its scope until it is retried or skipped. It is not the workspace's `/dead-letters` list, which holds events a rule could not evaluate, and it is not relayr's dead letters, which are inbound events the bridge could not publish. The page says so.
- `retry_run` makes a run that was dead, cancelled or skipped, or is waiting to retry, runnable now, with a fresh retry budget if it had finished. `skip_run` gives up on a run that is pending, retrying or dead, unblocking its scope. `cancel_run` stops a run that has not finished, and discards what a running attempt gives. Anything else is `InvalidState`.
- The commands are `retry_run`, `skip_run` (with an optional reason) and `cancel_run` (with an optional reason), each checked against `reflexr:retry_run`, `reflexr:skip_run` and `reflexr:cancel_run` on the workspace. A tenant's owners and admins hold them, as editors and workspace admins do.
- A command is carried out once per tenant, workspace, sender and `command_id`: a repeated id returns the first result and does nothing.
- Each action appends `run_requeued`, `run_skipped` or `run_cancelled` to the workspace's log, whose envelope records the actor and the time, and which carries a reason for the last two. grantr's audit log doesn't hold them.
- The app's own Runs shows a rule's runs live from the same stream, with Retry, Skip and Cancel as buttons that send at once.

The user decided five things:

1. All three actions are confirmed, with an optional reason for Skip and Cancel.
2. The list shows the runs that need attention, the dead-lettered and the retrying, by default, with a filter for every state.
3. Each run's detail shows who did what, from the events: requeue, skip and cancel, with the actor, the time and any reason.
4. Runs is live from the workspace's stream, as the app's is, and not refetched, with care for a connection for each workspace opened.
5. The scenarios may use an always-failing rule in the test application. The existing fixture, the triage rule that fails a ticket whose subject starts with "fail" (`tests/app/tickets.py`), is that rule; nothing is added to what ships.

## Decision

- **Admin's Runs goes beyond the RFC's read-only row.** It offers Retry, Skip and Cancel, as the app does, after a confirmation. This amends RFC-0002's admin table. The reads stay behind a grant: a person who may read runs and not act sees no button.
- **Runs is `/t/$tenant/runs`,** on the rail where `reflexr:read_runs` is allowed on the tenant, gated in `beforeLoad`.
  - The address keeps the workspace and the list (`?workspace=notes&show=all`). Without a workspace, the first of the tenant's, as artifactr lists them, is shown. A tenant has no tenant-wide runs read, so one workspace is shown at a time.
  - The list is **Needs attention** by default: the runs that are dead-lettered or retrying, newest first by when each started (its first attempt's place in the log); **Every state** shows all.
  - The actions each run offers are those its state takes in reflexr, where grantr allows them in that workspace (`allowedIn`, as the app does), and the server checks every command again.
  - A run row is its status as a word and a shape, its rule's name, why its last attempt failed as a code, how often it was retried, its attempts, and, folded, its history.
- **The stream is one, for the workspace shown, and goes with it.**
  - It is reflexr's stream alone, opened for the workspace chosen, not artifactr's.
  - The page is keyed by the tenant and the workspace, so choosing another closes the stream and opens another, and leaving Runs closes it; there is never more than one open.
  - It reconnects from where it was after a drop, reconnects with each refreshed token, and closes when the session ends, as the app's streams do. A closed stream is said, and the page asks for a reload.
  - Its hello asks for the run events alone (`run_started`, `run_retrying`, `run_requeued`, `run_succeeded`, `run_dead_lettered`, `run_cancelled`, `run_skipped`), which is all that Runs' store builds a run from. So the replay is of a workspace's runs, not its whole log, and the bodies of the application's events, which may hold what people said, never reach the admin's browser: the stream fails closed. A test holds the hello.
  - A stream that is refused for good (4400, 4401 or 4403), or closed, settles any command still unanswered as closed, and a command sent after says so at once, so a confirmed action never waits for ever.
  - While it is connecting the page says it is reading; after ten seconds without a welcome, as when reflexr is down, it says the runs can't be reached and that it keeps trying. When it has ended, the page says so in words of its own, never in the server's, which can echo what was sent.
  - `RunStreams` is keyed by the tenant and the workspace itself, so a stream and what was asked of it never carry over, whoever renders it.
- **Each action is confirmed and carried out once.**
  - Retry, Skip and Cancel each open an alert dialog that names the rule, the run and its attempts, says what the action does and what it can't undo, and has the action as its confirm. Skip and Cancel ask for an optional reason of at most 500 characters. Retry is in the primary colour; the others in the danger colour.
  - A command is sent only on confirming, on the stream, with a `command_id` of its own, which lasts as long as the dialog that asked for it is open. If the connection ends before the server answers, the store sends it again under the same id when it reconnects, and if the person tries again in that dialog after the stream said so, the same id is sent, so the server carries it out once. Any answer ends the id, a refusal included, and so does the dialog closing or being dismissed: a later intention is a new command under a new id, never one the server may answer from an earlier time, which would say "done" for a run that has dead-lettered again since.
  - Submitting the dialog again while the action is under way sends nothing more. When the button that opened a dialog is gone as it closes, since a retry takes the run from the list of those needing attention, focus goes to the list's heading, not to the page.
  - A refusal is said in the dialog, which stays: forbidden, no such run, a run that has changed (what it is now is in the row), or the server's own message. The run's row updates from the log, not from the answer.
- **What people did to a run stays with it.** The store keeps, for each run, the requeues, skips and cancels with their actor, time and reason, and the row lists them under "History". It is the log's own record, which reflexr keeps; admin adds no audit of its own, and grantr's Audit doesn't show these.
- **A run's last failure is a code, and is let go when the run is retried or succeeds.** A tenant admin sees `last failure: guardrail_blocked` only while it holds.
- **A run's error is not shown.** An action's error message can hold what a person or a model said, so the store keeps only the stable `reason` code the run failed with, and never the error. The run read in reflexr's own surfaces has the error for a person who needs it, which is the tenant's own data.
- **`RunList` and the rule-run status badge are `ui`'s,** moved from the app's Runs, which uses them as before. `ConfirmDialog` can ask for a reason, with a count of its characters, and have a calm confirm, for an action that loses nothing but is confirmed all the same, such as running something again.
- **The scenarios:** a ticket that fails is published as bob, and its run is waited for until it is dead-lettered. One asks to retry and thinks better of it: the run is as it was, with no history. Retrying, skipping with a reason and cancelling with a reason each show the run's history, with the reason; a skipped run leaves the runs that need attention and is in the list of every state; and the page says which dead letters these are. The viewer's refusal is the app's scenario, which holds the server's check.

## Options considered

| Option | For | Against |
|---|---|---|
| **Actions, confirmed, with history (chosen)** | An admin can unblock a scope from where they work; each act is deliberate and recorded | Beyond the RFC's read-only row, as amended here |
| Read-only, as the RFC says | Nothing to do wrongly | An admin sees a dead-lettered run and must go to the app, in a workspace, to act on it |
| Buttons that send at once, as the app's | One less step | A retry runs an action that may change things outside, and a skip unblocks a scope: neither is taken back |
| **The workspace's stream (chosen)** | Live, as the app's; the same store, the same commands | A connection for the workspace shown, and its log replayed on opening |
| Refetch the REST read after each command | No connection | Not live, and a run changed by someone else isn't seen until a refresh |
| Show a run's error | A person sees why | The error can hold what a person or a model said; a code is shown, and the error is in reflexr's own run read |

## Consequences

- Easier: a tenant's admin sees the runs that need someone, in any workspace, and unblocks a scope without leaving admin.
- Easier: each change to a run says who made it and why.
- Harder: Runs holds a stream open while it is shown, one at a time, and replays the log on opening.
- Accepted: a tenant-wide runs read doesn't exist, so a workspace is picked; the list of workspaces is artifactr's.
