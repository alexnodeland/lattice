# ADR-0032: The audit log, read from its end

**Status:** Accepted
**Date:** 2026-10-13
**Deciders:** Alex Nodeland

## Context

A read of the audit log pages forward from `after_seq`, oldest first, kept to some types or one subject ([ADR-0030](0030-the-audit-log-read-by-type-and-actor.md)). portalr's admin shows a tenant's audit log, and an admin opens it on what changed lately. Read forward, the newest entries are on its last page, and reaching it means reading every page before it.

artifactr's event log already reads from its end ([artifactr ADR-0005](../../artifactr/adr/0005-one-event-log-per-workspace.md)):

- a read takes the window `after_seq < seq < before_seq`;
- it returns the first `limit` of the window, or the last `last`, still oldest first;
- a client pages back with `before_seq` set to the oldest `seq` it holds.

## Decision

- **The audit log reads as artifactr's log does:**
  - `before_seq` closes the window `after_seq < seq < before_seq`.
  - `last` reads the last so many of the window, still oldest first. `limit` reads the first so many, as before. A read that gives neither reads the first 100, and one that gives both is `Invalid`, a 422 on the API, like artifactr's `_check_page`.
  - A client pages back with `last` and its oldest entry's `seq` as `before_seq`, with the same filter. A page shorter than `last` holds all there is.
  - It catches up with its newest entry's `seq` as `after_seq`, oldest first, and a page shorter than it asked for holds every new entry.
  - Both compose with the filter's types and subject.
- **Every surface takes them:**
  - `Grants.audit`;
  - the storage port's `audit`, and both adapters;
  - `GET /audit` and `GET /tenants/{tenant}/audit`, as `before_seq=` and `last=`.
- **SQL reads the last backwards.** It orders by `seq` descending with `last` as its limit, and turns the rows around, as artifactr's SQL adapter does. No index is added: the tenant's, the type's and the maker's each end in `seq`.
  - On PostgreSQL a page back by type, or by maker, is that index's range read backwards. A PostgreSQL test reads `EXPLAIN` on a long log for each.
  - SQLite may read the tenant's index and filter instead, once the window has two ends. Its logs are a contributor's or a test's, so that isn't tuned.
- **The tests run on memory, SQLite, PostgreSQL and row-level security,** as the storage contract does: the last, paged back to the first, with a type and with a subject, the last of a window between two entries, catching up, and both counts refused. The router's tests read both logs from their end, a window, and refuse both counts.
- **portalr's client is regenerated** from the committed schema.

## Options considered

| Option | For | Against |
|---|---|---|
| **`before_seq` and `last`, as artifactr's log (chosen)** | One convention across lattice's logs; a page is oldest first wherever it's read from | A newest-first view turns each page around |
| A `newest_first` flag, paging back by `before_seq` | Pages arrive in display order | A second convention beside artifactr's, for the same need |
| A cursor, opaque to the caller | Free to change how it pages | A token to decode where a sequence number says it plainly |
| Read forward to the last page in the UI | Nothing in grantr | Every page read to show the newest |

## Consequences

- Easier: an admin opens the log on what changed last, and a client that reads artifactr's log already knows how to page grantr's.
- Harder: on SQLite, a page back by type or maker may read the tenant's index and filter; only PostgreSQL's plan is held by a test.
