# Architecture decision records

Each record captures one decision: the context that forced it, the options considered, and the consequences we accepted. Records are immutable once accepted; a changed decision gets a new record that amends or supersedes the old one. Proposals that precede decisions live in [`../rfcs/`](../rfcs/README.md).

ADR-0001 to ADR-0009 record the decisions D1 to D9 of [lattice RFC-0001](../../rfcs/0001-grantr-identity-and-access.md), the design grantr implements, and ADR-0010 onwards the decisions made building it. The family's own decisions, such as how lattice checks and releases every package, are [lattice's ADRs](../../adr/README.md).

| ADR | Title | Status |
|---|---|---|
| [0001](0001-the-hook-hears-the-action.md) | The hook hears the action | Accepted |
| [0002](0002-grants-down-to-threads-and-artifacts.md) | Grants down to threads and artifacts | Accepted |
| [0003](0003-visible-to-the-workspace-unless-restricted.md) | Visible to the workspace unless restricted | Accepted, amended by 0024 |
| [0004](0004-an-agent-turn-acts-for-its-user.md) | An agent turn acts for its user | Accepted |
| [0005](0005-a-users-tenants-from-grantrs-memberships.md) | A user's tenants from grantr's memberships | Accepted |
| [0006](0006-what-v0-1-includes.md) | What v0.1 includes | Accepted |
| [0007](0007-an-append-only-audit-log.md) | An append-only audit log | Accepted |
| [0008](0008-grantrs-own-model-with-openfga-shaped-ports.md) | grantr's own model, with OpenFGA-shaped ports | Accepted |
| [0009](0009-a-deployment-wide-operator-role.md) | A deployment-wide operator role | Accepted, amended by 0014 and 0019 |
| [0010](0010-commands-bounded-by-what-their-maker-holds.md) | Commands bounded by what their maker holds | Accepted |
| [0011](0011-built-in-roles-over-the-catalogs.md) | Built-in roles over the catalogs | Accepted, amended by 0019, 0022 and 0023 |
| [0012](0012-every-item-an-access-names-and-hooks-typed-by-actor.md) | Every item an access names, and hooks typed by their actor | Accepted |
| [0013](0013-transactions-by-tenant-and-one-audit-log.md) | Transactions by tenant, and one audit log | Accepted, amended by 0016 |
| [0014](0014-an-operator-enters-a-tenant-by-granting-themselves.md) | An operator enters a tenant by granting themselves | Accepted |
| [0015](0015-a-check-writes-nothing.md) | A check writes nothing | Accepted, amended by 0024 |
| [0016](0016-the-sql-adapter.md) | The SQL adapter | Accepted, amended by 0024 |
| [0017](0017-the-admin-api.md) | The admin API | Accepted |
| [0018](0018-telemetry-through-the-api.md) | Telemetry through the OpenTelemetry API | Accepted |
| [0019](0019-runtime-actions-and-the-application-role.md) | Runtime actions, and the application role | Accepted, amended by 0022 and 0025 |
| [0020](0020-the-rule-role.md) | The rule role | Accepted, amended by 0029 |
| [0021](0021-the-deployments-own-tools.md) | The deployment's own tools | Accepted, amended by 0025 |
| [0022](0022-a-tenants-members-list-its-workspaces.md) | A tenant's members list its workspaces | Accepted |
| [0023](0023-portalrs-admin-reads.md) | portalr's admin reads | Accepted |
| [0024](0024-who-sees-a-restricted-item.md) | Who sees a restricted item | Accepted |
| [0025](0025-the-application-lists-tenants-and-workspaces-and-writes-for-code-rules.md) | The application lists tenants and workspaces, and writes for its code rules | Accepted, amended by 0027 and 0029 |
| [0026](0026-row-level-security-under-the-scoping.md) | Row-level security under the scoping | Accepted |
| [0027](0027-the-application-installs-the-rules-people-accept.md) | The application installs the rules people accept | Accepted |
| [0028](0028-a-principals-id-cant-pass-for-the-libraries-actors.md) | A principal's id can't pass for the libraries' actors | Accepted |
| [0029](0029-a-stored-rule-acts-as-itself-in-its-own-workspace.md) | A stored rule acts as itself, in its own workspace | Accepted |
| [0030](0030-the-audit-log-read-by-type-and-actor.md) | The audit log, read by type and by actor | Accepted |
| [0031](0031-the-catalog-read.md) | The catalog, read | Accepted |
| [0032](0032-the-audit-log-read-newest-first.md) | The audit log, read newest first | Accepted |

To add a record, copy lattice's [ADR template](../../adr/template.md) to the next number and add a row above.
