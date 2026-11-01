# ADR-0093: Approvals on their own page, and a confirmation on admin's confirm page alone

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** lattice [RFC-0011](../../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md)'s portalr approvals list and page, and [ADR-0038](../../adr/0038-approval-asked-by-tiers-a-union-resolved-setting-names-and-admin-high-confirmed-by-its-caller.md)'s confirm page (O15), at the address lattice [RFC-0014](../../rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md) gives it; on grantr [ADR-0040](../../grantr/adr/0040-approvals-over-the-admin-api-read-by-who-may-answer-them-answered-on-portalrs-pages.md)

## Context

grantr answers approvals over its admin API (grantr ADR-0040): the pending ones a person may answer, one approval as it stands, and an answer, which names the page it was given on, `portalr` or `portalr:confirm`. A call that waits for a person's yes, from an agent's run, a code session or an outside client, now has an `Approval`, but no page shows it. RFC-0011 asks for an approvals list and an approval's page, where a web push will also link. ADR-0038 makes an `admin_high` call wait for its caller's own confirmation on "portalr's signed-in confirm page", answered nowhere else, and RFC-0014 puts that page at `/portalr/admin/confirm/{id}`, where "the page names the action and its target and asks them to type the target's name". portalr has to settle:

- where the list and the page live, since approvals come from every workspace;
- how a page with no tenant in its address reads an approval, whose reads are each in a tenant;
- what the person types, since an approval names no target apart from the call's arguments;
- what the page shows to one who may see an approval but not answer it.

## Decision

- **The app lists the approvals waiting for the reader**, at `/t/$tenant/approvals`, oldest first, from every workspace, in the frame the tenant's workspaces are listed in, linked from that page. Each row says what is asked, who asked, through which client, in which workspace and when. The list is grantr's `answerable` read, so a row is one the reader may answer.
- **An approval's page is `/t/$tenant/approvals/$approval`**. It shows what the call would do (its summary, its diff or else its arguments, and a plan's steps it would allow), with each character a reader wouldn't see shown as its code point, as the thread's approval card does. It also shows who asked, the capability and its version, the workspace, when it was asked and when it expires, or who answered, when, on which page and why. ui's `ApprovalDetails` draws this for both pages.
  - **Approve and Deny** answer on `portalr`, with a reason if one is given, bound to the arguments shown by their digest. A refusal, such as a first answer that came before or a deadline passed, is said on the page, which then reads the approval again and shows how it was settled.
  - The buttons are shown only to one the store lists the approval for. The person it was asked for, who may not answer it, sees where it stands. Anyone else is told it isn't there, as grantr tells them.
- **A confirmation is answered on admin's confirm page alone**, `/portalr/admin/confirm/$approval`:
  - The app's list and page link a confirmation there, and never answer one.
  - Its address names the approval alone, as a client or a push links to it. The page asks each of the person's tenants, in order, until one shows the approval; a tenant that doesn't (404 or 403) is skipped, and any other failure is the page's to show.
  - It reads the approval afresh each time it opens, never from the cache, so what is confirmed is the approval as it stands.
  - **The person types the tenant's name before Confirm does anything.** Every `admin_high` action acts on its tenant (deleting it, revoking its key, granting its roles, defining its roles, making an operator in it), and the tenant is the one target every approval names. A typed name stops a confirmation given in the wrong tenant, or by a press alone. Cancel needs no name.
  - Only the person a confirmation was asked of, by name, sees Confirm. An approval that isn't a confirmation links to its page in the app.
- **Neither page is recorded** by session replay: both are listed in the app's routes, and `main` is blocked on them, as on every page that doesn't allow it (ADR-0077).

## Options considered

### Option A: The list in the app, the confirm page in admin (chosen)

**Pros:** a person answers what waits for them where they work, whatever their role; the confirm page is at the address RFC-0014 gives, where the `admin_high` actions' people are.
**Cons:** a confirmation is one page away from the list, in the other UI.

### Option B: Type the action's target, as named by the capability

**Pros:** closer to RFC-0014's "the target's name": the key's id, the role's name.
**Cons:** neither lattice-core's `Rendering` nor its `Capability` names which argument is the target, so the page would guess from the arguments. Naming it is a contract change, which belongs with portr's confirmations (#918).

### Option C: Approvals under each workspace

**Cons:** the store lists approvals per tenant, a run's approval is in the workspace it runs in, and a person with approvals in four workspaces would open four pages.

## Consequences

- Easier: an agent's call that needs a yes can be answered in portalr, and an `admin_high` call through an outside client can be confirmed, which makes grantr's commands' `admin_high` set usable.
- Harder: the confirm page reads one tenant after another, which is a read per tenant the person is in before the approval's.
- The thread's approval card still answers artifactr's deferred calls through `answer_deferred`. Answering one backed by an `Approval` through `Approvals.answer` comes with artifactr's deferred approvals (RFC-0011).
- Web push's link to an approval's page comes with notifications (#952), and "Needs you" in a workspace's frame doesn't count approvals yet.

## Action items

1. [x] The app's approvals list and page, admin's confirm page, ui's `ApprovalDetails`, and the client's reads and answer, with a scenario for each.
2. [ ] Typing the action's own target, once the approval contract names one (#918).
3. [ ] The approvals in "Needs you", and web push's link (#952).
