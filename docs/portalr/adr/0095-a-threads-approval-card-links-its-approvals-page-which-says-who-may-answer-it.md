# ADR-0095: A thread's approval card links its approval's page, which says who may answer it

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** the follow-up artifactr [ADR-0101](../../artifactr/adr/0101-a-run-paused-on-an-enforcers-approval-names-it-and-is-answered-in-its-store.md) leaves, on [ADR-0093](0093-approvals-on-their-own-page-and-a-confirmation-on-admins-confirm-page-alone.md)'s approval page

## Context

A call that lattice's enforcer defers pauses its run, and its request names the approval it waits on: `DeferredRequest.approval` (artifactr ADR-0101). The thread shows the request as an approval card, with Approve and Deny. An answer there is the store's, given as the person who presses. The store says who may give it, and refuses anyone else.

So a reader in the thread could press Approve and be refused, without knowing who may answer, or by when. The approval's own page (ADR-0093) shows what the call would do, who asked, when it expires and where it stands. It didn't say who may answer either, though grantr's `ApprovalView` carries its `answerers`.

## Decision

- **The card links its approval's page.** An approval card whose request names an approval has a link, "Who may answer it", to `/t/$tenant/approvals/$approval`. It sits under the call's arguments, before Approve and Deny, as a ghost button, so it doesn't compete with them. `Request` takes the link as `approval`, the router's own element, as an artifact's card takes `open` (ADR-0061). A request that names none, such as a connected app's call that the thread answers itself, has no link.
- **The page says who may answer, while it waits.** A "Who may answer" row, before "Expires", lists the client's `answerersOf(approval, me, names)`:
  - "anyone who holds" its grantr action;
  - each subject it names: "you", or the person by their email;
  - "the members of group" each of its groups;
  - then, if the answer must come from someone else, "except" the person it was asked for, or "whoever asked";
  - for a confirmation, the one subject, "on the confirm page".
- **The page looks up the subjects it names:** `peopleIn` adds them to the people it finds by their email. Once answered, expired or withdrawn, the row goes, and who answered, or why it closed, is shown instead.
- The thread's Approve and Deny stay. The link is for one who wonders whether they may, or who must be asked.

## Options considered

### Option A: A link to the page, and the page says who may (chosen)

**Pros:** one place says who may answer, kept with the rest of what an approval is. The thread reads nothing more for it.
**Cons:** a reader leaves the thread to find out.

### Option B: Say who may answer on the card itself

**Pros:** no click.
**Cons:** the thread would read each waiting approval from grantr, and look up its people, for every reader of the thread, as it renders. An approval card already holds the call's arguments and its review, and is sized to keep Approve and Deny in the window (ADR-0087).

## Consequences

- Easier: a reader in a thread finds who may answer an approval, and the page an approver would answer it on, in one click.
- Easier: the approval page says who may answer to anyone who opens it, among them the person it was asked for, who can't answer it.
- Harder: the page names the subjects an approval names, so it looks up more people by their email.
