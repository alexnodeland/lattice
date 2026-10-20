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
| [0010](0010-the-client-generated-types-and-resumable-stores.md) | The client: generated types, and resumable stores | Accepted, amended by artifactr 0063, reflexr 0061 and reflexr 0064 |
| [0011](0011-the-router-and-its-readers.md) | The router and its readers | Accepted, amended by 0012 and 0041 |
| [0012](0012-acceptance-against-a-two-tenant-stack.md) | Acceptance against a two-tenant stack | Accepted |
| [0013](0013-the-apps-scenarios-against-the-test-application.md) | The app's scenarios, against the test application with Supabase Auth | Accepted |
| [0014](0014-the-apps-shell.md) | The app's shell: English strings, a committed route tree, and Supabase Auth's client | Accepted |
| [0015](0015-the-chat-components-and-streamdown.md) | The chat's components, and Markdown through Streamdown | Accepted, amended by 0043 |
| [0016](0016-the-threads-area.md) | The Threads area: a workspace's stream, and a scripted agent to chat with | Accepted |
| [0017](0017-the-artifacts-and-proposals-areas.md) | The Artifacts and Proposals areas: renderers by kind, and diffs by revision | Accepted |
| [0018](0018-the-runs-area-and-feedback.md) | The Runs area, feedback on runs, and what a person may do | Accepted |
| [0019](0019-the-kits-look.md) | The kit's look: a side rail, labelled icons, raised surfaces and quiet statuses | Accepted, amended by 0036 |
| [0020](0020-the-rules-area.md) | The Rules area: stored rules as reflexr's JSON, sent over its REST | Accepted |
| [0021](0021-the-areas-on-the-frame-and-what-admin-needs.md) | The areas on the frame, a danger colour, budget badges, and what admin's frame decides | Accepted |
| [0022](0022-restricting-and-sharing-a-thread.md) | Restricting and sharing a thread, from its menu | Accepted, amended by 0038 |
| [0023](0023-admins-shell-and-home.md) | admin's shell and Home: its own tenant, every tenant for operators, and a card per read | Accepted |
| [0024](0024-access-members-groups-and-keys.md) | Access: members, groups and keys, each where grantr allows its read | Accepted, amended by 0038 |
| [0025](0025-access-roles-and-grants.md) | Access: roles and grants, on grantr's catalog | Accepted |
| [0026](0026-audit.md) | Audit: grantr's log, newest on top, filtered by type and maker | Accepted |
| [0027](0027-feedback-and-evaluations.md) | Feedback and evaluations, summed by day, and the first charts | Accepted, amended by 0036 |
| [0028](0028-usage-and-spend.md) | Usage and spend, per day and per workspace, against the budget's share | Accepted |
| [0029](0029-ui-polish-from-the-screenshots.md) | UI polish from the screenshots: one width rule, titles, a violet focus ring | Accepted |
| [0030](0030-traces-and-the-trace-view.md) | Traces, and a trace view written for `ui` | Accepted |
| [0031](0031-logs-and-health.md) | Logs without their lines, and a Health section | Accepted |
| [0032](0032-runs-in-admin.md) | Runs in admin, with Retry, Skip and Cancel | Accepted |
| [0033](0033-third-party-notices-for-the-bundled-javascript.md) | Third-party notices for the JavaScript the UIs bundle | Accepted |
| [0034](0034-tenants-and-the-deployments-audit.md) | Tenants in admin, created by email, and the deployment's audit log | Accepted, amended by 0038 |
| [0035](0035-tools-and-the-record-of-opening-them.md) | Tools, links into Langfuse and Grafana, and the record of making them | Accepted |
| [0036](0036-the-chart-theme-and-colour-blind-mode.md) | The chart theme: violet-led series, patterns only where marks touch, and a hook for colour-blind mode | Accepted, amended by 0047 |
| [0037](0037-form-controls-and-row-actions.md) | Form controls and row actions: a Base UI select, form fields, segmented windows, button variants and sizes | Accepted |
| [0038](0038-people-by-email.md) | People by email, not by id | Accepted |
| [0039](0039-elevation-status-colour-states-and-density.md) | Elevation, status colours, alerts and placeholders, and admin's compact density | Accepted |
| [0040](0040-scenarios-against-a-generated-application-and-size-budgets.md) | Scenarios against a generated application, and size budgets | Accepted, amended by 0044 |
| [0041](0041-first-party-webassembly-in-the-apps-policy.md) | First-party WebAssembly in the UIs' policy | Accepted, amended 2026-10-17 |
| [0042](0042-mermaid-cant-draw-under-the-policy.md) | Mermaid can't draw in the page under the policy, so it is parked | Accepted |
| [0043](0043-markdowns-basics.md) | Markdown's basics: code blocks, callouts, footnotes per message, copying, an add-ons seam, and tests under the policy | Accepted, amended by 0044, 0045, 0047 and 0041 (2026-10-17) |
| [0044](0044-highlighting-and-math-on-demand.md) | Highlighting and math, loaded on demand, each with a size budget of its own | Accepted, amended by 0047 |
| [0045](0045-integrations-in-admin-and-the-apps-read-of-them.md) | Integrations in admin, and the app's read of them: each its default where unread, and read again on `not_enabled` | Accepted, amended by 0047 |
| [0046](0046-tracker-links-on-runs.md) | Tracker links on runs: what a run's chain filed, and the items that set it off | Accepted |
| [0047](0047-dashboards-on-demand-tables-and-the-panel-registry.md) | Dashboards on demand, tables by TanStack Table, the panel registry, and one seam for integrations | Accepted |
| [0048](0048-native-files-in-the-app.md) | Native files in the app: the manifest, who has the file, its pages, a download, and its words compared | Accepted |
| [0049](0049-checking-a-native-file-out-and-in.md) | Checking a native file out and in: the editor on its own origin, an upload with its progress, and a retry that is safe | Accepted |
| [0050](0050-a-native-files-proposals-and-the-pilots-scenarios.md) | A native file's proposals: outdated, never rebased, and compared page by page; and the check-out pilot's scenarios | Accepted |
| [0051](0051-mini-apps-the-sandboxed-frame-and-its-bridge.md) | Mini apps: the sandboxed frame and its bridge | Accepted |

To add a record, copy lattice's [ADR template](../../adr/template.md) to the next number and add a row above.
