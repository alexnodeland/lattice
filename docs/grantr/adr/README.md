# Architecture decision records

Each record captures one decision: the context that forced it, the options considered, and the consequences we accepted. Records are immutable once accepted; a changed decision gets a new record that amends or supersedes the old one. Proposals that precede decisions live in [`../rfcs/`](../rfcs/README.md).

ADR-0001 to ADR-0009 record the decisions D1 to D9 of [lattice RFC-0001](../../rfcs/0001-grantr-identity-and-access.md), the design grantr implements, and ADR-0010 onwards the decisions made building it. The family's own decisions, such as how lattice checks and releases every package, are [lattice's ADRs](../../adr/README.md).

| ADR | Title | Status |
|---|---|---|
| [0001](0001-the-hook-hears-the-action.md) | The hook hears the action | Accepted |
| [0002](0002-grants-down-to-threads-and-artifacts.md) | Grants down to threads and artifacts | Accepted |
| [0003](0003-visible-to-the-workspace-unless-restricted.md) | Visible to the workspace unless restricted | Accepted |
| [0004](0004-an-agent-turn-acts-for-its-user.md) | An agent turn acts for its user | Accepted |
| [0005](0005-a-users-tenants-from-grantrs-memberships.md) | A user's tenants from grantr's memberships | Accepted |
| [0006](0006-what-v0-1-includes.md) | What v0.1 includes | Accepted |
| [0007](0007-an-append-only-audit-log.md) | An append-only audit log | Accepted |
| [0008](0008-grantrs-own-model-with-openfga-shaped-ports.md) | grantr's own model, with OpenFGA-shaped ports | Accepted |
| [0009](0009-a-deployment-wide-operator-role.md) | A deployment-wide operator role | Accepted; amended by 0014 |
| [0010](0010-commands-bounded-by-what-their-maker-holds.md) | Commands bounded by what their maker holds | Accepted |
| [0011](0011-built-in-roles-over-the-catalogs.md) | Built-in roles over the catalogs | Accepted |
| [0012](0012-every-item-an-access-names-and-hooks-typed-by-actor.md) | Every item an access names, and hooks typed by their actor | Accepted |
| [0013](0013-transactions-by-tenant-and-one-audit-log.md) | Transactions by tenant, and one audit log | Accepted; amended by 0016 |
| [0014](0014-an-operator-enters-a-tenant-by-granting-themselves.md) | An operator enters a tenant by granting themselves | Accepted |
| [0015](0015-a-check-writes-nothing.md) | A check writes nothing | Accepted |
| [0016](0016-the-sql-adapter.md) | The SQL adapter | Accepted |
| [0017](0017-the-admin-api.md) | The admin API | Accepted |
| [0018](0018-telemetry-through-the-api.md) | Telemetry through the OpenTelemetry API | Accepted |

To add a record, copy lattice's [ADR template](../../adr/template.md) to the next number and add a row above.
