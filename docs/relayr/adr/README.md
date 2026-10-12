# Architecture decision records

Each record captures one decision: the context that forced it, the options considered, and the consequences we accepted. Records are immutable once accepted; a changed decision gets a new record that amends or supersedes the old one. Proposals that precede decisions live in [`../rfcs/`](../rfcs/README.md).

ADR-0001 to ADR-0007 record the decisions D1 to D7 of [stackr RFC-0002](../../stackr/rfcs/0002-the-combined-system.md), the design relayr implements.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-relayr-its-own-repository-and-package.md) | relayr, its own repository and package | Accepted, partly superseded by 0013 |
| [0002](0002-the-outbound-actor-an-external-agent-per-rule.md) | The outbound actor, an `ExternalAgentActor` per rule | Accepted |
| [0003](0003-a-thread-is-never-a-chain.md) | A thread is never a chain | Accepted |
| [0004](0004-sessions-linked-not-continued.md) | Sessions linked, not continued | Accepted |
| [0005](0005-where-a-rules-source-of-truth-lives.md) | Where a rule's source of truth lives | Accepted |
| [0006](0006-bridged-types-in-the-artifactr-namespace.md) | Bridged types in the `artifactr` namespace | Accepted |
| [0007](0007-notices-by-default.md) | Notices by default | Accepted |
| [0008](0008-trunk-based-development-with-rfcs-and-adrs.md) | Trunk-based development with RFCs, ADRs and evergreen docs | Accepted, amended by 0013 |
| [0009](0009-quality-gates.md) | Quality gates | Accepted, amended by 0013 |
| [0010](0010-mit-license.md) | MIT license | Accepted |
| [0011](0011-documentation-site-and-brand.md) | The documentation site and brand | Accepted, amended by 0014 |
| [0012](0012-the-libraries-pinned-by-git-revision.md) | The libraries pinned by git revision | Superseded by 0013 |
| [0013](0013-relayr-in-lattice.md) | relayr in lattice | Accepted |
| [0014](0014-one-site-for-the-family.md) | One site for the family | Accepted |
| [0015](0015-cursors-leases-and-dead-letters-in-the-ledger.md) | Cursors, leases and dead letters in the ledger | Accepted |
| [0016](0016-followers-start-on-open.md) | Followers start on open | Accepted |
| [0017](0017-the-follower-acts-as-the-application.md) | The follower acts as the application | Accepted |
| [0018](0018-bridged-events-their-fields-ids-and-projections.md) | Bridged events, their fields, ids and projections | Accepted |

To add a record, copy lattice's [ADR template](../../adr/template.md) to the next number and add a row above.
