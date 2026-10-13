# ADR-0030: The audit log, read by type and by actor

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

portalr's admin shows a tenant's audit log, filtered by what changed and by who changed it (lattice RFC-0002). grantr's reads of the log took only a sequence number to read after and a page size. A filter in the browser would see only the pages it had loaded, so it would page through a busy log to find one person's changes, and could show an empty page while matching entries waited further on. The maintainer chose to filter in grantr.

## Decision

- **A read of the audit log takes an `AuditFilter`:**
  - the event types to keep, or every type when it names none;
  - `by`, the one subject whose changes to keep, or anyone's when it's None.
  - It keeps paging by `after_seq`: a page's last sequence number reads on from there, with the same filter.
- **The subject is the subject itself,** as an entry's `by` holds it: a user, a service principal, a rule principal by its workspace and rule, or the agent. An entry is kept when its maker equals it, so a person and a principal with the same id stay apart, and so do two rules whose workspaces and names would read alike joined together, such as (`a`, `b/c`) and (`a/b`, `c`). The first operator's grant, which no one made, is kept only by a filter that names no one.
- **`AuditType` names every event's `type`,** and a test holds it to the events.
- **Every surface takes it:**
  - `Grants.audit(keep=)`;
  - the storage port's `audit`, and both adapters;
  - on `GET /audit` and `GET /tenants/{tenant}/audit`: `type=`, which may repeat, and the subject in structured parameters: `actor_kind=` (`user`, `service_principal`, `rule` or `agent`), `actor=` (a user's or principal's id, or a rule's name), and `workspace=` (a rule's).
  - The parameters must name one subject. A kind without what it needs, with more than it takes, an id a principal can't have, or an unknown type is a 422.
- **In SQL, the type and the maker are columns.** The maker is stored as a grant's subject is: `actor_kind`, `actor_workspace` and `actor_id`, with `""` for a part it doesn't have, and `""` in all three for no one.
  - They are indexed after the tenant and before the sequence number: `ix_grantr_audit_event_type`, and `ix_grantr_audit_actor` over the three.
  - A single type, or a single subject, is one index's range; a type and a subject together are an index's range and a filter.
  - `append` fills them from the event and its maker.
- **Migration 0004** adds the columns and fills them from each entry's JSON.
  - It works a thousand entries at a time, one batch of updates each, after the last chunk's sequence number, so no cursor stays open while it updates.
  - It keeps its own copy of how makers were stored, so it fills what it filled then, whatever the code becomes. It refuses a maker of a kind no entry could have had.
  - It runs as the tables' owner, which row-level security doesn't hold, so every tenant's entries are filled.
  - It holds `grantr_audit` exclusively until it commits, so changes to access wait for it.
- **The tests run on memory, SQLite, PostgreSQL and row-level security,** as the storage contract does. Every kind of maker is appended and found again. The migration's fill, its refusal and its downgrade with entries present are tested on SQLite and PostgreSQL, in CI's Check job, which has PostgreSQL.

## Options considered

| Option | For | Against |
|---|---|---|
| **Filter in grantr, by indexed columns (chosen)** | A page is what was asked for, however busy the log | Four columns, two indexes, and a migration |
| Filter in the browser, over loaded pages | Nothing changes in grantr | A filter sees only what was loaded; a page can come back empty |
| Filter in grantr, inside the JSON | No migration | No index for it; JSON queries differ between SQLite and PostgreSQL |
| **The maker in a subject's columns, and a `Subject` to filter by (chosen)** | Unambiguous, as grants are stored; a filter is the subject itself | Three parameters to name one on the API |
| One string per maker, such as `rule:<workspace>/<rule>` | One parameter | Workspaces and rule names are free strings, so two rules can read alike, and the encoding is frozen into rows |

## Consequences

- Easier: portalr's admin, and any reader of the log, asks for one type of change or one subject's changes and pages through only those.
- Harder: an event type added later needs its name in `AuditType`, which the test enforces.
- Harder: upgrading a deployment with a long audit log holds that table for as long as migration 0004 takes.
