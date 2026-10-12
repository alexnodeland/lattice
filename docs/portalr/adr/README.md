# Architecture decision records

Each record captures one decision: the context that forced it, the options considered, and the consequences we accepted. Records are immutable once accepted; a changed decision gets a new record that amends or supersedes the old one. Proposals that precede decisions live in [`../rfcs/`](../rfcs/README.md).

ADR-0001 to ADR-0006 record the decisions P1 to P6 of [lattice RFC-0002](../../rfcs/0002-portalr-the-portal.md), the design portalr implements. ADR-0007 and ADR-0008 are phase 1's, and ADR-0009 phase 2's.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-a-router-the-application-mounts.md) | A router the application mounts | Accepted |
| [0002](0002-react-and-tanstack-as-two-static-single-page-apps.md) | React and TanStack, as two static single-page apps | Accepted |
| [0003](0003-a-chat-of-its-own.md) | A chat of its own | Accepted |
| [0004](0004-native-views-of-a-tenants-observability.md) | Native views of a tenant's observability | Accepted |
| [0005](0005-operators-see-across-tenants.md) | Operators see across tenants | Accepted |
| [0006](0006-shared-stores-every-read-filtered.md) | Shared stores, every read filtered | Accepted |
| [0007](0007-typescript-7-and-6-only-where-a-tool-needs-its-api.md) | TypeScript 7, and TypeScript 6 only where a tool needs its API | Accepted |
| [0008](0008-the-bun-workspace-runs-in-bun.md) | The Bun workspace runs in Bun | Accepted |
| [0009](0009-ui-tested-in-chromium-in-both-schemes-under-bun.md) | `ui` tested in Chromium, in both schemes, under Bun | Accepted |

To add a record, copy lattice's [ADR template](../../adr/template.md) to the next number and add a row above.
