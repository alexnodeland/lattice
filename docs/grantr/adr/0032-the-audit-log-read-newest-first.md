# ADR-0032: The audit log, read newest first

**Status:** Accepted
**Date:** 2026-10-13
**Deciders:** Alex Nodeland

## Context

A read of the audit log pages forward from `after_seq`, oldest first, kept to some types or one subject ([ADR-0030](0030-the-audit-log-read-by-type-and-actor.md)). portalr's admin shows a tenant's audit log, and an admin opens it for what changed lately. Read forward, the newest entries are on its last page, and reaching it means reading every page before it.

## Decision

- **A read may run newest first, and stop before an entry:**
  - `newest_first`, false by default, reads from the newest entry back.
  - `before_seq`, none by default, keeps only the entries before that sequence number.
  - A newest-first page reads on with its last entry's `seq` as the next page's `before_seq`, with the same filter.
  - Both compose with `after_seq` and with the filter's types and subject. `after_seq` and `before_seq` together read the entries between two, either way.
- **Every surface takes them:**
  - `Grants.audit`;
  - the storage port's `audit`, and both adapters;
  - `GET /audit` and `GET /tenants/{tenant}/audit`, as `newest_first=` and `before_seq=`. A `before_seq` below 1 is a 422.
- **No index is added.** The tenant's, the type's and the maker's indexes each end in `seq`, so a newest-first read is the same range read backwards, which PostgreSQL and SQLite both do.
- **The tests run on memory, SQLite, PostgreSQL and row-level security,** as the storage contract does: newest first, paged back, with a type, with a subject, and a window between two entries oldest first. The router's tests read both logs newest first.
- **portalr's client is regenerated** from the committed schema.

## Options considered

| Option | For | Against |
|---|---|---|
| **`newest_first` and `before_seq` (chosen)** | Pages back the way `after_seq` pages forward; one more parameter for each direction | Two parameters more |
| An `order` of `asc` or `desc`, paging by `after_seq` in either | One parameter | `after_seq` would mean "before" when descending |
| A cursor, opaque to the caller | Free to change how it pages | A token to decode where a sequence number says it plainly |
| Read forward to the last page in the UI | Nothing in grantr | Every page read to show the newest |

## Consequences

- Easier: an admin opens the log on what changed last.
- Harder: nothing more to index; a type and a subject together remain an index's range and a filter, in either direction.
