# ADR-0063: A stored rule's history, read by its name

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

A stored rule's row holds only its current version and provenance. Its history is in the log, as its `reflexr:rule_installed` and `reflexr:rule_archived` facts ([ADR-0053](0053-stored-rules-one-fixed-configuration.md)). Each fact names the actor that made the change, and an install's carries its provenance.

relayr needs that history for its rules from chat ([lattice #137](https://github.com/alexnodeland/lattice/issues/137)):

- which artifact and proposal relayr last installed a rule from, after someone else changed it;
- which rule an artifact installed;
- whether an acceptance was installed already.

`read` filters only by type. So relayr read the latest 1,000 install facts on every install and every drift run, and an install older than those was invisible to it ([relayr ADR-0030](../../relayr/adr/0030-drift-proposed-back-to-a-rules-artifact.md)).

## Decision

- **`Workspace.rule_history(rule)` returns a stored rule's versions, oldest first:** its install and archive facts, as envelopes, with their actors.
  - An archived rule keeps its history.
  - A rule never stored, such as a code rule, has an empty one.
  - It asks `reflexr:read_rules` for the rule, as `get_rule` does: the history is that rule's record, and a grant on one rule should reach it. `reflexr:read_events` would ask about the whole log, which someone granted only on a rule doesn't hold.
  - So someone granted `reflexr:read_rules` on a single rule now sees more than `get_rule` shows: its past definitions and provenance, `approved_by` and all, who made each change, and each fact's trace and causation ids. Those are that rule's own record, and nothing about other rules or events.
- **Every surface has it.**
  - REST: `GET /workspaces/{workspace_id}/rules/{rule}/history`.
  - MCP: the `rule_history` tool, as JSON lines.
- **`Storage.rule_history(workspace, name)` is a new protocol method.** `stored_rule_of(envelope)` says which rule, if any, an envelope is a version of, so every storage agrees on it.
  - `InMemoryStorage` scans its log.
  - `SqlStorage` adds a `rule` column to `reflexr_events`, set from `stored_rule_of` on append, and a partial index on the tenant, workspace, rule and `seq`, over the rows that have one. A rule's history is then one range, however long the log.
- **Migration 0008** adds the column and fills it in one statement, which scans the log for the install and archive facts and reads each one's `event.rule` from its stored JSON. Then it creates the index. The same statement runs on SQLite and PostgreSQL, as migration 0003's did.
- **Provenance stays opaque.** No read filters by it. A caller that wants a rule by where it came from finds the rule's name where it came from: relayr reads the names from the artifact's revisions, then their histories ([relayr ADR-0032](../../relayr/adr/0032-a-rules-installs-read-from-its-history.md)).
- **No paging, and no default bound on MCP.** A rule's versions are its changes, which people make one at a time, and read alone. A `last` bound would need storage, `Workspace`, REST and MCP to take it, check it and agree on it, as `read`'s does, for histories that are short.

## Options considered

| Option | For | Against |
|---|---|---|
| **A dedicated history read, over an indexed column (chosen)** | Says what it reads, as artifactr's `revisions` does; one range per rule | A protocol method, a column and a migration |
| A `rule=` filter on `read` | Reuses `read`'s window and paging | `rule` means something only on two fact types, and `actor.rule` already means "made by the rule" |
| A filter on any field of the event, or on provenance | General | JSON paths differ between SQLite and PostgreSQL, no index backs them, and provenance is the installer's, not reflexr's, to read |
| A table of rule versions, written beside each fact | No column on the log | A second write to keep in step with the fact it copies |

## Consequences

- Easier: relayr finds its installs however far back they are. portalr's Rules area can show who changed a rule, and when.
- Harder: a `Storage` implemented outside reflexr implements one more method. A column on the log, null on every other row, and a partial index are kept beside it.
- Harder: on PostgreSQL, migration 0008 holds `reflexr_events` exclusively while it scans the log twice, to fill the column and to build the index, inside `migrate`'s one transaction. Schedule it for when the log may pause. Building the index `CONCURRENTLY`, outside a transaction, is out of scope.
- Revisit: paging, if rules come to be changed by machines often enough for a history to grow long.
