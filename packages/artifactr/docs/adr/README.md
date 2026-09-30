# Architecture decision records

Each record captures one decision: the context that forced it, the options considered, and the consequences we accepted. Records are immutable once accepted; a changed decision gets a new record that amends or supersedes the old one. Proposals that precede decisions live in [`../rfcs/`](../rfcs/README.md).

| ADR | Title | Status |
|---|---|---|
| [0001](0001-python-library-with-sans-io-core.md) | Python library with a sans-IO core | Accepted |
| [0002](0002-single-write-path.md) | One write path: commands through `Workspace.commit` | Accepted |
| [0003](0003-artifact-types-as-pydantic-subclasses.md) | Artifact types are Pydantic subclasses with library-defined patch kinds | Accepted |
| [0004](0004-optimistic-concurrency-and-revisions.md) | Optimistic concurrency and append-only revisions | Accepted |
| [0005](0005-one-event-log-per-workspace.md) | One durable event log per workspace | Accepted, amended by 0021 |
| [0006](0006-agent-integration-as-pydantic-ai-capability.md) | Agent integration as a pydantic-ai capability | Accepted, amended by 0017 |
| [0007](0007-caller-owned-live-output.md) | Live output is owned by the caller, not the log | Accepted |
| [0008](0008-agent-perception-and-steering.md) | Agent perception: change notes, fresh rendering, steering | Accepted |
| [0009](0009-write-policies-and-non-blocking-proposals.md) | Write policies and non-blocking proposals | Accepted |
| [0010](0010-pausing-with-deferred-tools.md) | Pausing with pydantic-ai deferred tools | Accepted |
| [0011](0011-workspace-scoped-artifacts-and-tenant-handles.md) | Workspace-scoped artifacts and tenant-scoped handles | Accepted |
| [0012](0012-surfaces-websocket-rest-mcp.md) | Surfaces: WebSocket thread protocol, REST commands, MCP | Superseded by 0048 |
| [0013](0013-library-with-reference-implementation.md) | A library with adapters and a reference implementation | Accepted |
| [0014](0014-trunk-based-development-with-rfcs-and-adrs.md) | Trunk-based development with RFCs, ADRs and evergreen docs | Accepted |
| [0015](0015-quality-gates.md) | Quality gates | Accepted |
| [0016](0016-mit-license.md) | MIT license | Accepted |
| [0017](0017-application-toolsets-and-capability-events.md) | Application toolsets register on the agent; the capability emits capability events | Accepted |
| [0018](0018-core-host-contract.md) | Core's host contract: needs, commit and record | Accepted |
| [0019](0019-storage-protocol-and-workspace-handles.md) | One storage protocol behind workspace handles | Accepted |
| [0020](0020-running-agents-in-threads.md) | Running agents in threads | Accepted |
| [0021](0021-sql-storage.md) | SQL storage with one dialect-neutral implementation | Accepted |
| [0022](0022-surfaces-over-one-command-handler.md) | Surfaces over one command handler | Superseded by 0048 |
| [0023](0023-documentation-site.md) | The documentation site | Accepted, amended by 0026 and 0050 |
| [0024](0024-reference-implementation-as-a-workspace-member.md) | The reference implementation as a workspace member | Accepted |
| [0025](0025-distribution-name.md) | Distributed as artifactr-ai, imported as artifactr | Accepted |
| [0026](0026-publishing-the-documentation-site.md) | Publishing the documentation site from main | Accepted, amended by 0050 |
| [0027](0027-opentelemetry-observability-with-langfuse.md) | OpenTelemetry-native observability, with Langfuse primary | Accepted |
| [0028](0028-typed-feedback-as-events.md) | Typed feedback as events, mirrored to Langfuse | Accepted |
| [0029](0029-evalr-shared-eval-kit.md) | evalr, a shared eval kit | Accepted |
| [0030](0030-compose-and-dev-containers.md) | Contributor Compose and dev containers here, infrastructure in stackr | Accepted |
| [0031](0031-litellm-proxy-first.md) | LiteLLM, proxy first, for routing and guardrails | Accepted |
| [0032](0032-libraries-and-the-stackr-template.md) | Libraries, and stackr as the infrastructure template | Accepted |
| [0033](0033-trace-links-on-runs-and-revisions.md) | Trace links on runs and revisions | Accepted |
| [0034](0034-ports-and-adapters-for-integrations.md) | Ports and adapters for integrations | Accepted |
| [0035](0035-a-turn-is-its-own-trace.md) | A turn is its own trace | Accepted |
| [0036](0036-metric-cardinality-through-sdk-views.md) | Metric cardinality through SDK views | Accepted |
| [0037](0037-feedback-targets-and-evaluators.md) | Feedback targets and evaluators | Accepted |
| [0038](0038-feedback-as-scores.md) | Feedback as scores, through ports | Superseded by 0049 |
| [0039](0039-the-langfuse-adapter.md) | The Langfuse adapter | Accepted; its score adapters superseded by 0049 |
| [0040](0040-joining-stackrs-network.md) | Joining stackr's network when it runs | Accepted |
| [0041](0041-dashboards-generated-tested-and-released.md) | Dashboards generated, tested and released | Accepted |
| [0042](0042-typed-run-failures.md) | Typed run failures | Accepted |
| [0043](0043-the-litellm-adapter.md) | The LiteLLM adapter | Accepted |
| [0044](0044-the-evalr-adapter.md) | The evalr adapter | Accepted; its amendment superseded by 0049 |
| [0045](0045-a-message-id-is-used-once.md) | A message id is used once in a workspace | Accepted |
| [0046](0046-telemetry-that-composes-across-libraries.md) | Telemetry that composes across libraries, untraced polling and mirror cursors | Accepted |
| [0047](0047-cancel-safe-storage.md) | Cancel-safe storage | Accepted |
| [0048](0048-surfaces-over-the-runner.md) | Surfaces over the runner | Accepted |
| [0049](0049-scores-on-evalr.md) | Scores on evalr | Accepted |
| [0050](0050-one-docs-build.md) | One docs build | Accepted |
| [0051](0051-notices.md) | Notices: messages that start no turn | Accepted |

To add a record, copy [`template.md`](template.md) to the next number and add a row above.
