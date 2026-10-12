# Architecture decision records

Each record captures one decision: the context that forced it, the options considered, and the consequences we accepted. Records are immutable once accepted; a changed decision gets a new record that amends or supersedes the old one. Proposals that precede decisions live in [`../rfcs/`](../rfcs/README.md).

ADR-0001 to ADR-0009 record the decisions D1 to D9 of [lattice RFC-0001](../../rfcs/0001-grantr-identity-and-access.md), the design grantr implements. The family's own decisions, such as how lattice checks and releases every package, are [lattice's ADRs](../../adr/README.md).

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
| [0009](0009-a-deployment-wide-operator-role.md) | A deployment-wide operator role | Accepted |

To add a record, copy lattice's [ADR template](../../adr/template.md) to the next number and add a row above.
