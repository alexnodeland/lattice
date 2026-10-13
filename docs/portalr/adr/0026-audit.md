# ADR-0026: Audit: grantr's log, newest on top, filtered by type and maker

**Status:** Accepted
**Date:** 2026-10-13
**Deciders:** Alex Nodeland

## Context

lattice RFC-0002 gives admin an Audit area: grantr's audit log for a tenant, paged and filtered, for its admins. grantr reads the log:

- filtered by event type and by one subject ([grantr ADR-0030](../../grantr/adr/0030-the-audit-log-read-by-type-and-actor.md));
- from its end back, with `last` and `before_seq`, as artifactr's log is read ([grantr ADR-0032](../../grantr/adr/0032-the-audit-log-read-newest-first.md)).

Reading it takes `grantr:read_audit` on the tenant, which owners and admins hold.

## Decision

- **Audit is `/t/$tenant/audit`,** on the rail where grantr allows `grantr:read_audit`.
  - The rail's one read of grantr's checks asks it beside Access's actions.
  - The route is gated in `beforeLoad` and reads in `loader`, as Access's parts are (ADR-0024).
  - Opened by its address where it isn't allowed, it says so in the tenant's frame. A failed read says so there, through admin's `ReadFailed`, which Access shares, with a way to read it again, and, where the address has a filter, a way to clear it, so a filter grantr refuses isn't a dead end.
- **It opens on the newest changes.**
  - `client`'s `audit(tenant, filter)` is an infinite query. Each page is the last 50 before the previous page's oldest entry, and a page short of 50 is the first.
  - Each page comes oldest first, so the table turns each around, and the newest is on top. "Show more" reads the page before.
  - A log of exactly 50 shows "Show more" once: the page before is empty, and then it goes.
  - "Show more" stays focusable while it reads. How many changes are shown is a status, so a reader hears the count when a page arrives and when "Show more" goes.
  - A page before that can't be read says so, as an alert, and the log stays.
  - A change to access on any screen reads the log again, as `changedAccess` stales everything grantr answers in the tenant.
- **Each entry reads as a sentence,** with who made it and when, and each row, or card, is named by its sentence and its time:
  - "added ci (service principal)";
  - "granted viewer on workspace notes to ops (group)".
  - `said(event)` covers each of grantr's 14 event types in an exhaustive switch, so a new type fails the typecheck.
  - The maker is a member, a rule, "the agent", or "no one" for the first operator's grant. People and principals are named with their kind, the tenant's first owner too.
- **Times are absolute, in the reader's zone, with the relative time on hover,** as ADR-0021 asks of the audit log: `ui`'s `Moment` is a `<time>` titled from `Intl.RelativeTimeFormat`. app's rules list uses it too.
- **The filter is in the address,** so a filtered log can be linked to.
  - It takes one type of change, or any. grantr takes several, which the UI doesn't offer yet.
  - It takes who made it: a person or a service principal by id, a rule by its name and workspace, or the agent.
  - The read uses only a filter grantr takes: a kind without what it needs, or a person's or a principal's id grantr can't hold (a `:`, a `~` or a space), is dropped from the route's search, and the form shows what was read. A number or a yes in the address is read as text, and every value is trimmed; the id field's pattern says what grantr takes.
  - A maker is matched exactly, by kind and id, as grantr matches it.
- **The scenario:** alice adds a service principal, filters Audit to members added, and finds it at the top.

## Options considered

| Option | For | Against |
|---|---|---|
| **Read from the end, with grantr's `last` (chosen)** | Opens on what changed last; one read | grantr needed it first (ADR-0032) |
| Read forward from the first entry | Nothing new in grantr | The newest on the last page |
| **The filter in the address (chosen)** | A filtered log can be linked to, and Back undoes a filter | The form and the address are kept in step |
| The filter in the screen's state | Simpler | Lost on reload, and not shareable |

## Consequences

- Easier: the log can be read where it happened, as a sentence, filtered by what changed or who did it.
- Harder: people are named by their ids, which for a person is Supabase Auth's UUID, as on Members (ADR-0024).
