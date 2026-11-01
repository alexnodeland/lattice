# ADR-0039: The enforcer's gate and audit answered by grantr, each call as the person it is for

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** lattice [RFC-0011](../../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md)'s grantr row, `Authorize` and `Audit` for the enforcer; beside [ADR-0038](0038-approvals-stored-per-tenant-answered-by-grantrs-subjects-groups-and-grants.md)

## Context

lattice-core's enforcer (lattice [ADR-0037](../../adr/0037-the-enforcement-path-in-lattice-core-refusals-by-step-approvals-resumed-by-id.md)) asks two ports on every call:

- **`Authorize`:** whether the caller, in the call's scope, holds the capability's grantr action.
- **`Audit`:** where the call's one `CapabilityCalled` entry goes.

RFC-0011 has grantr answer both. A call's caller is a person, or an agent's run or a code session, each acting for a person or for no one, and it may come through an outside client. grantr's subjects are users, service principals, rules and the agent acting for no one, which holds nothing.

## Decision

- **`Grants.authorize(subject_of=subject_of_call)`** returns the enforcer's `Authorize`:
  - It is `check` of the action on the call's workspace, as the call's subject.
  - A person, calling for themselves or through an outside client, is checked as their `User`: the client acts for them (lattice RFC-0014).
  - An agent's run or a code session acting for a person is checked as that person. One acting for no one is `Agent()`, which holds nothing, so it is refused.
  - The agent's tier ceiling stays the enforcer's own step.
  - A call that names an id no tenant can have, such as `~deployment`, holds nothing.
  - An application may pass its own `subject_of`.
- **`Grants.capability_audit()`** returns the enforcer's `Audit`:
  - Each call is one `capability_called` entry in its tenant's audit log, made by the person it was for, or by the agent where it was for no one.
  - The entry holds the capability and version, workspace, caller, client, correlation id, surface, arguments' digest, each step, the outcome, the approval and when it was called. It never holds the arguments or the output.
  - A call that names a tenant that doesn't exist, or an id no tenant can have, is recorded in the deployment's log with the tenant it named, so the operators see a forged scope.
  - Recording never refuses: the enforcer records in its `finally`, and a failed record would replace the call's outcome.
- **portalr's admin** reads the entry as a sentence ("called artifactr.edit_text in workspace notes, as run:run_1 through Claude (conn_1): refused"), and its filter offers "Capabilities called".

## Options considered

### Option A: The person a call is for (chosen)

**Pros:** an agent's run can do no more than its person, and the outside client changes nothing of what is held. That matches how artifactr's provider builds its actor (artifactr ADR-0099).
**Cons:** a stored workflow's run that acts for no one is the agent here, though reflexr runs it as its rule's principal. reflexr's provider, when it comes, passes a `subject_of` that knows its rules.

### Option B: A subject of its own for each run and session

**Cons:** grantr would need a grant per run, and nothing grants them: a run would hold nothing, or something no one chose.

## Consequences

- Easier: an application composes the enforcer from grantr with two calls, and every call is in the audit log admin already shows.
- Harder: the audit log grows by one entry per call, in the same table as access changes; a read filters by type to leave them out.
- `secret_read`, the secrets port's audit, comes with the Supabase Vault adapter.
- A retention for these entries, apart from access changes', is its own change (#904).

## Action items

1. [x] `authorize`, `capability_audit` and the `capability_called` event, tested on memory, SQLite and PostgreSQL with row-level security, and admin's sentence.
2. [ ] reflexr's provider, with a `subject_of` that knows its stored rules' principals.
3. [ ] `secret_read`, with the Supabase Vault adapter.
