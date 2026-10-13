# Architecture decision records

Each record captures one decision: the context that forced it, the options considered, and the consequences we accepted. Records are immutable once accepted; a changed decision gets a new record that amends or supersedes the old one. Proposals that precede decisions live in [`../rfcs/`](../rfcs/README.md).

ADR-0001 to ADR-0006 record the decisions P1 to P6 of [lattice RFC-0002](../../rfcs/0002-portalr-the-portal.md), the design portalr implements. ADR-0007 and ADR-0008 are phase 1's, ADR-0009 phase 2's, ADR-0010 phase 3's, and ADR-0011 phase 4's.

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
| [0010](0010-the-client-generated-types-and-resumable-stores.md) | The client: generated types, and resumable stores | Accepted, amended by artifactr 0063 and reflexr 0061 |
| [0011](0011-the-router-and-its-readers.md) | The router and its readers | Accepted, amended by 0012 |
| [0012](0012-acceptance-against-a-two-tenant-stack.md) | Acceptance against a two-tenant stack | Accepted |
| [0013](0013-the-apps-scenarios-against-the-test-application.md) | The app's scenarios, against the test application with Supabase Auth | Accepted |
| [0014](0014-the-apps-shell.md) | The app's shell: English strings, a committed route tree, and Supabase Auth's client | Accepted |
| [0015](0015-the-chat-components-and-streamdown.md) | The chat's components, and Markdown through Streamdown | Accepted |
| [0016](0016-the-threads-area.md) | The Threads area: a workspace's stream, and a scripted agent to chat with | Accepted |
| [0017](0017-the-artifacts-and-proposals-areas.md) | The Artifacts and Proposals areas: renderers by kind, and diffs by revision | Accepted |
| [0018](0018-the-runs-area-and-feedback.md) | The Runs area, feedback on runs, and what a person may do | Accepted |
| [0019](0019-the-kits-look.md) | The kit's look: a side rail, labelled icons, raised surfaces and quiet statuses | Accepted |
| [0020](0020-the-rules-area.md) | The Rules area: stored rules as reflexr's JSON, sent over its REST | Accepted |
| [0022](0022-restricting-and-sharing-a-thread.md) | Restricting and sharing a thread, from its menu | Accepted |

To add a record, copy lattice's [ADR template](../../adr/template.md) to the next number and add a row above.
