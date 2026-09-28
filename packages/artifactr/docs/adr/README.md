# Architecture decision records

Each record captures one decision: the context that forced it, the options considered, and the consequences we accepted. Records are immutable once accepted; a changed decision gets a new record that amends or supersedes the old one. Proposals that precede decisions live in [`../rfcs/`](../rfcs/README.md).

| ADR | Title | Status |
|---|---|---|
| [0001](0001-python-library-with-sans-io-core.md) | Python library with a sans-IO core | Accepted |
| [0002](0002-single-write-path.md) | One write path: commands through `Workspace.commit` | Accepted |
| [0003](0003-artifact-types-as-pydantic-subclasses.md) | Artifact types are Pydantic subclasses with library-defined patch kinds | Accepted |
| [0004](0004-optimistic-concurrency-and-revisions.md) | Optimistic concurrency and append-only revisions | Accepted |
| [0005](0005-one-event-log-per-workspace.md) | One durable event log per workspace | Accepted |
| [0006](0006-agent-integration-as-pydantic-ai-capability.md) | Agent integration as a pydantic-ai capability | Accepted, amended by 0017 |
| [0007](0007-caller-owned-live-output.md) | Live output is owned by the caller, not the log | Accepted |
| [0008](0008-agent-perception-and-steering.md) | Agent perception: change notes, fresh rendering, steering | Accepted |
| [0009](0009-write-policies-and-non-blocking-proposals.md) | Write policies and non-blocking proposals | Accepted |
| [0010](0010-pausing-with-deferred-tools.md) | Pausing with pydantic-ai deferred tools | Accepted |
| [0011](0011-workspace-scoped-artifacts-and-tenant-handles.md) | Workspace-scoped artifacts and tenant-scoped handles | Accepted |
| [0012](0012-surfaces-websocket-rest-mcp.md) | Surfaces: WebSocket thread protocol, REST commands, MCP | Accepted |
| [0013](0013-library-with-reference-implementation.md) | A library with adapters and a reference implementation | Accepted |
| [0014](0014-trunk-based-development-with-rfcs-and-adrs.md) | Trunk-based development with RFCs, ADRs and evergreen docs | Accepted |
| [0015](0015-quality-gates.md) | Quality gates | Accepted |
| [0016](0016-mit-license.md) | MIT license | Accepted |
| [0017](0017-application-toolsets-and-capability-events.md) | Application toolsets register on the agent; the capability emits capability events | Accepted |
| [0018](0018-core-host-contract.md) | Core's host contract: needs, commit and record | Accepted |
| [0019](0019-storage-protocol-and-workspace-handles.md) | One storage protocol behind workspace handles | Accepted |
| [0020](0020-running-agents-in-threads.md) | Running agents in threads | Accepted |

To add a record, copy [`template.md`](template.md) to the next number and add a row above.
