# API reference

The reference is generated from the library's docstrings and type annotations. It documents each package's public API: the names in its `__all__`. Anything else is internal and may change without notice.

## Packages

The packages are layers. Each depends only on the ones below it, so each is usable without the ones above ([Architecture](../architecture.md#layers)).

| Package | What it holds | Install |
|---|---|---|
| [`artifactr.core`](core.md) | Every rule, as pure functions over immutable values: artifact types, actors, commands, events, patches, rejections, change notes and the protocol's frames | core |
| [`artifactr.telemetry`](telemetry.md) | Tracing and metrics through the OpenTelemetry API: span attribution and the metric registry | core |
| [`artifactr.workspace`](workspace.md) | Tenant-scoped workspace handles, the storage protocol and in-memory storage | core |
| [`artifactr.agent`](agent.md) | The pydantic-ai capability, the session, the runner and live output | core |
| [`artifactr.scores`](scores.md) | Feedback as scores: the mapping, the mirror that follows the log, and the ports scores leave through | core |
| [`artifactr.sql`](sql.md) | SQL storage on PostgreSQL and SQLite, and its migrations | `sql`, `postgres` or `sqlite` extra |
| [`artifactr.fastapi`](fastapi.md) | The thread protocol over WebSocket, and REST, as a FastAPI router | `fastapi` extra |
| [`artifactr.otel`](otel.md) | `configure_telemetry`: the OpenTelemetry SDK, exporters and instrumentations, and metric views | `otel` extra |
| [`artifactr.mcp`](mcp.md) | An MCP server for external agents | `mcp` extra |

The wire formats have their own pages: the [thread protocol](../protocol.md) and its [JSON Schema](schema.md).

## The top-level package

`artifactr` re-exports the names most applications need, so `from artifactr import Workspaces, Runner` works. Each is documented in its layer:

| Name | Documented in |
|---|---|
| `Artifact`, `MarkdownArtifact`, `Versioned`, `WritePolicy` | [`artifactr.core`: Artifacts](core.md#artifacts) |
| `new_id` | [`artifactr.core`: Identifiers](core.md#identifiers) |
| `Actor`, `UserActor`, `AgentActor`, `ExternalAgentActor`, `SystemActor` | [`artifactr.core`: Actors](core.md#actors) |
| `Applied`, `Proposed`, `Resolved`, `Recorded` | [`artifactr.core`: Outcomes](core.md#outcomes) |
| `Rejection`, `VersionConflict`, `NotFound` | [`artifactr.core`: Rejections](core.md#rejections) |
| `JsonPatch`, `TextEdit`, `TextEdits` | [`artifactr.core`: Patches](core.md#patches) |
| `Workspaces`, `Workspace`, `InMemoryStorage` | [`artifactr.workspace`](workspace.md) |
| `ArtifactWorkspace`, `Session`, `Runner`, `RunHandle`, `ArtifactDraft` | [`artifactr.agent`](agent.md) |

`artifactr.__version__` is the installed version.
