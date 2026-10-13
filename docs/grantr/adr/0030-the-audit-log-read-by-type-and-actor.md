# ADR-0030: The audit log, read by type and by actor

**Status:** Accepted
**Date:** 2026-10-13
**Deciders:** Alex Nodeland

## Context

portalr's admin shows a tenant's audit log, filtered by what changed and by who changed it (lattice RFC-0002). grantr's reads of the log took only a sequence number to read after and a page size. A filter in the browser would see only the pages it had loaded, so it would page through a busy log to find one person's changes, and could show an empty page while matching entries waited further on. The maintainer chose to filter in grantr.

## Decision

- **A read of the audit log takes an `AuditFilter`:** the event types to keep, every type when it names none, and one actor whose changes to keep, anyone's when it names no one. It keeps paging by `after_seq`: a page's last sequence number reads on from there, with the same filter.
- **An actor is named by kind and id,** `actor_of(subject)`: `user:<id>`, `service_principal:<id>`, `rule:<workspace>/<rule>`, or `agent`. A person and a principal with the same id stay apart, and a principal's id can't hold a `:` ([ADR-0028](0028-a-principals-id-cant-pass-for-the-libraries-actors.md)), so a name can't pass for another. The first operator's grant, which no one made, has no actor and is kept only by a filter that names no one.
- **`AuditType` names every event's `type`,** and a test holds it to the events.
- **Every surface takes it:** `Grants.audit(keep=)`, the storage port's `audit`, both adapters, and `type=`, which may repeat, and `actor=` on `GET /audit` and `GET /tenants/{tenant}/audit`. An unknown type or an empty actor is a 422.
- **In SQL, the type and the actor are columns, each indexed after the tenant and before the sequence number,** `ix_grantr_audit_type` and `ix_grantr_audit_actor`, so a filtered page is a range read of one index. `append` fills them from the event and its maker. Migration 0004 adds them and fills them from each entry's JSON, with its own copy of how actors were named, so it fills what it filled then whatever the code becomes. It runs as the tables' owner, which row-level security doesn't hold, so every tenant's entries are filled. The type is required once they are.
- **The tests run on memory, SQLite, PostgreSQL and row-level security,** as the storage contract does, and the migration's fill is tested on SQLite and PostgreSQL from entries written under 0003.

## Options considered

| Option | For | Against |
|---|---|---|
| **Filter in grantr, by indexed columns (chosen)** | A page is what was asked for, however busy the log | Two columns, an index each, and a migration |
| Filter in the browser, over loaded pages | Nothing changes in grantr | A filter sees only what was loaded; a page can come back empty |
| Filter in grantr, inside the JSON | No migration | No index for it; JSON queries differ between SQLite and PostgreSQL |
| **An actor named by kind and id (chosen)** | A user and a principal with the same id stay apart | A name to build, not an id |
| An actor named by id alone | Simpler to ask for | A user and a principal with one id would mix |

## Consequences

- Easier: portalr's admin, and any reader of the log, asks for one type of change or one person's changes and pages through only those.
- Harder: an event type added later needs its name in `AuditType`, which the test enforces.
