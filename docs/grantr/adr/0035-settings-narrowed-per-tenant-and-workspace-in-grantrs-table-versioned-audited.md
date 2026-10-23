# ADR-0035: Settings narrowed per tenant and workspace, in grantr's table, versioned and audited

**Status:** Proposed
**Date:** 2026-10-22
**Deciders:** Alex Nodeland
**Implements:** lattice [ADR-0030](../../adr/0030-settings-typed-declared-in-lattice-core-and-only-narrowed-below.md); beside [ADR-0034](0034-integrations-switched-per-tenant-and-workspace-in-grantrs-table-audited.md)

## Context

lattice ADR-0030 declares settings in lattice-core and has a store hold the tenant's and the workspace's layers. grantr already holds tenant-scoped admin state, with row-level security and an audit log written in the same transaction as each change ([ADR-0034](0034-integrations-switched-per-tenant-and-workspace-in-grantrs-table-audited.md)).

## Decision

- **Table `grantr_settings`** (migration 0007).
  - Columns: `tenant_id`, `workspace` (empty for the tenant), `key`, `value` (JSON, null once unset), `version`, `written` (who and when) and `profile_version` (null for now).
  - The primary key is `(tenant_id, workspace, key)`, and the table has the same row-level security policy as every grantr table.
  - Unsetting keeps the row with a null value, so its version keeps counting.
- **`Grants(settings=, operator_settings=)`:** the registry, `KNOWN_SETTINGS` by default, and the operator's layer, which is checked when the deployment starts.
- **`Grants.value(tenant, workspace, key)` implements lattice-core's `Settings` port.** It reads the store on every call and checks no one, as `is_enabled` doesn't. It answers the setting's floor when the store can't be read, when the tenant id is malformed, or when the workspace id is empty. A well-formed id naming a tenant that doesn't exist has nothing stored, so it gets the operator's value or the default. The tenant's layer and the workspace's are read in two reads, so a change made between them can be seen half done; the next call reads both again.
- **`Grants.settings(...)` and `Grants.set_setting(...)`:**
  - Both require the new `grantr:manage_settings` on the tenant or on the workspace. Tenant owners and admins hold it, and workspace admins hold it within their workspace.
  - A level the setting's `lowest` doesn't reach is refused, and an operator-only setting is never written through grantr.
  - A value of the wrong kind, or wider than the layer above, is `Invalid`; the message names the ceiling and the layer that set it.
  - A `version` that isn't the level's current one is `Stale`.
  - Setting what is already set records nothing.
  - Each change appends `setting_set` (key, workspace, old, new, version) in the same transaction.
- **REST:**
  - `GET /tenants/{t}/settings` and `GET /tenants/{t}/workspaces/{w}/settings` return every layer, the ceiling, which layer set the ceiling, and the effective value; clamped rows are flagged, and keys no registry declares are listed apart.
  - `PUT /tenants/{t}[/workspaces/{w}]/settings/{key}` takes `{"value": number | names | null}`, with `If-Match: "<version>"` (`"0"` for a setting never set). It answers with the new state and its `ETag`.
  - `If-Match` is optional: without it the last write wins. `If-Match: *` names no version and is refused (422). A GET carries each setting's version in its body, not as an `ETag` header, since one response holds many settings.
  - Who may is checked before what is asked. A route's dependency checks `grantr:manage_settings`, then reads `If-Match`, before the body is validated, so a caller without the grant gets 403 whatever its body or `If-Match` holds. The document still declares the body (`SettingChange`) and the `If-Match` header.
  - Two things are refused before anyone is checked: a body that isn't JSON, which is read before any dependency, and a tenant id outside its pattern, which is refused as the path is matched. Both are 422.
  - A workspace id or key longer than 256 characters is refused (422) before anything is stored.
  - Refusals use the refusal schema: 409 `version_conflict`, 422 `invalid`, 403 `forbidden`.
  - The value is strict: a boolean, a string or a float is refused.

## Consequences

- Easier: one store and one audit trail for every admin-set value.
- Harder: a registry change can leave rows no setting reads. They are kept and listed, never applied.
- The audit log's tamper-resistance (an append-only role, or a hash chain) is a separate item.
