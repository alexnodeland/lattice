# Thread protocol v1

> **Status:** draft. Field names may change before the first release; the structure is settled by [ADR-0005](adr/0005-one-event-log-per-workspace.md), [ADR-0007](adr/0007-caller-owned-live-output.md) and [ADR-0012](adr/0012-surfaces-websocket-rest-mcp.md).

Clients connect to a workspace over WebSocket. They receive the workspace's durable events with resume, send commands, and receive live frames for runs they are watching. REST exposes the same commands and the same reads.

## Connection

- **Endpoint:** `GET /v1/workspaces/{workspace_id}/stream`, upgraded to WebSocket with subprotocol `artifactr.v1`.
- **Authentication** is resolved by the host application before the socket is accepted. The host supplies `resolve_actor(request) -> (tenant_id, Actor)`; failure closes the socket with `4401`.
- **Frames** are UTF-8 JSON text frames, one message per frame.
- **One reader per socket.** The server reads inbound frames in a single loop and never awaits long work in it. Commands are dispatched as tasks, so a `stop_run` is never stuck behind a slow command.

## Handshake and resume

```mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: WebSocket upgrade (subprotocol artifactr.v1)
    S-->>C: accept (actor resolved)
    C->>S: hello {protocol, resume_after_seq, threads}
    S-->>C: welcome {protocol, head_seq, active_runs}
    S-->>C: event frames with seq > resume_after_seq
    S-->>C: replay_complete {up_to_seq}
    Note over C,S: Then: event frames as they commit, live frames for watched runs, command results
```

```json
{"type": "hello", "protocol": "artifactr.v1", "resume_after_seq": 1041, "threads": ["th_9"]}
```

```json
{
  "type": "welcome",
  "protocol": "artifactr.v1",
  "workspace_id": "ws_1",
  "head_seq": 1057,
  "active_runs": [{"run_id": "run_42", "thread_id": "th_9"}]
}
```

- **The server owns the protocol version.** An unsupported `protocol` closes the socket with `4400`.
- **Resume is by `seq`, never by timestamp.** The server subscribes to the log from `resume_after_seq` before replaying, so no event can fall between replay and live delivery.
- `resume_after_seq` of `0` replays from the beginning of retained history. If the requested position is older than retention, the server sends a `snapshot` frame and then events after the snapshot's `seq`.
- `threads` filters thread-scoped events (messages, runs). Workspace-scoped events (artifacts, proposals) are always delivered.
- A `hello` not received within the server's timeout closes the socket with `4408`.

## Server frames

### `event`: durable

Every durable event arrives in the same envelope. The stored envelope and the wire frame have the same shape.

```json
{
  "type": "event",
  "seq": 1042,
  "id": "01J9ZK4Q7V3M8X2R5T6Y0B1C2D",
  "ts": "2026-09-28T14:03:11.204Z",
  "workspace_id": "ws_1",
  "thread_id": "th_9",
  "run_id": "run_42",
  "actor": {"kind": "agent", "run_id": "run_42"},
  "event": {
    "type": "artifact_changed",
    "artifact_id": "plan_1",
    "kind": "plan",
    "version": 8,
    "patch_kind": "json_patch",
    "patch": [{"op": "replace", "path": "/tasks/t3/status", "value": "done"}],
    "summary": "Marked 'Ship v1' done"
  }
}
```

`actor.kind` is one of `user`, `agent`, `external_agent` or `system`.

| `event.type` | Scope | Fields |
|---|---|---|
| `thread_created` | thread | `title` |
| `focus_changed` | thread | `artifact_ids` |
| `user_message` | thread | `message_id`, `content`, `client_message_id?` |
| `assistant_message` | thread, run | `message_id`, `content` |
| `run_started` | thread, run | `trigger` (`message`, `resume`, `api`) |
| `tool_called` | run | `tool_call_id`, `tool_name`, `args_summary` |
| `tool_returned` | run | `tool_call_id`, `status` (`ok`, `error`, `retry`), `summary` |
| `run_paused` | run | `requests`: list of `{tool_call_id, kind: question \| approval, prompt, schema?}` |
| `run_ended` | run | `status` (`completed`, `stopped`, `failed`), `usage` |
| `artifact_created` | workspace | `artifact_id`, `kind`, `version`, `data` |
| `artifact_changed` | workspace | `artifact_id`, `kind`, `version`, `patch_kind`, `patch`, `summary` |
| `artifact_archived` | workspace | `artifact_id`, `version` |
| `proposal_created` | workspace | `proposal_id`, `artifact_id?`, `kind`, `base_version`, `patch_kind`, `patch`, `rationale?` |
| `proposal_resolved` | workspace | `proposal_id`, `decision` (`accepted`, `rejected`), `changes?`, `version?` |
| `app_event` | any | `name`, `data` |

`patch_kind` is `json_patch` (RFC 6902) or `text_edits` (a list of `{old, new}` replacements, where each `old` occurs exactly once in the document).

### `live`: ephemeral

Live frames carry a run's token-level output. They have no `seq`, are not stored, and delivery is best-effort. `after_seq` is the last durable `seq` at emission, as an ordering hint.

```json
{"type": "live", "run_id": "run_42", "after_seq": 1042, "event": {"type": "text_delta", "part": 0, "delta": "Here is the"}}
```

| `event.type` | Fields | Source |
|---|---|---|
| `part_started` | `part`, `part_kind` (`text`, `thinking`, `tool_call`), `tool_name?` | pydantic-ai `PartStartEvent` |
| `text_delta` | `part`, `delta` | `PartDeltaEvent` |
| `thinking_delta` | `part`, `delta` | `PartDeltaEvent` |
| `tool_args_delta` | `part`, `delta` | `PartDeltaEvent` |
| `part_ended` | `part` | `PartEndEvent` |
| `draft` | `artifact_id?`, `kind`, `data` | a tool's `ctx.emit(...)`: a full snapshot of an artifact being generated, not yet committed |
| `app_live` | `name`, `data` | other application `CustomEvent`s |

Durable events supersede live frames. When `assistant_message` arrives, it is the authoritative text for that message. When `artifact_changed` arrives, it replaces any `draft` for that artifact.

Clients receive live frames for runs in the threads they subscribed to. `watch_run` attaches to a specific run.

### `command_result`

Every command gets exactly one result.

```json
{"type": "command_result", "command_id": "c_17", "ok": true, "outcome": "applied", "seq": 1043}
```

```json
{
  "type": "command_result",
  "command_id": "c_18",
  "ok": false,
  "rejection": {"type": "version_conflict", "base": 7, "head": 8, "changes_since": [1042]}
}
```

`outcome` is `applied` or `proposed`. `rejection.type` is one of `version_conflict`, `validation_failed`, `patch_failed`, `not_found` or `forbidden`.

### `replay_complete` and `snapshot`

```json
{"type": "replay_complete", "up_to_seq": 1057}
```

```json
{"type": "snapshot", "as_of_seq": 900, "artifacts": [], "threads": []}
```

The snapshot's contents are an [open question](architecture.md#open-questions).

## Client frames: commands

Every command carries a client-chosen `command_id`, which is also an idempotency key: the server deduplicates repeated ids within a window.

| `type` | Fields | Effect |
|---|---|---|
| `create_thread` | `title?` | `thread_created` |
| `post_message` | `thread_id`, `content`, `client_message_id?` | `user_message`. Starts a run if the thread has none active; otherwise the message steers the active run. |
| `stop_run` | `run_id` | Cancels the run; `run_ended` with status `stopped`. |
| `answer` | `run_id`, `tool_call_id`, `answer` or `approved` | Records the answer. Once every pending request is answered, the paused run resumes. |
| `create_artifact` | `kind`, `data` | `artifact_created` |
| `edit_artifact` | `artifact_id`, `base_version`, `patch_kind`, `patch` | `artifact_changed`, or `proposal_created` under the type's write policy |
| `archive_artifact` | `artifact_id`, `base_version` | `artifact_archived` |
| `respond_to_proposal` | `proposal_id`, `decision`, `changes?` | `proposal_resolved`, plus `artifact_changed` when accepted |
| `set_focus` | `thread_id`, `artifact_ids` | `focus_changed` |
| `watch_run` | `run_id` | Attaches this socket to the run's live frames |

```json
{
  "type": "edit_artifact",
  "command_id": "c_18",
  "artifact_id": "plan_1",
  "base_version": 7,
  "patch_kind": "json_patch",
  "patch": [{"op": "add", "path": "/tasks/t9", "value": {"title": "Write changelog"}}]
}
```

## Close codes

| Code | Meaning | Client action |
|---|---|---|
| `1000` | Normal closure | none |
| `1001` | Server going away | reconnect and resume |
| `4400` | Unsupported protocol version | upgrade the client |
| `4401` | Unauthenticated | re-authenticate |
| `4403` | Actor may not access this workspace | stop |
| `4408` | `hello` not received in time | reconnect |
| `4429` | Too many connections or rate limited | back off, then reconnect |

## REST

REST mirrors the commands and exposes reads. Command bodies are the same JSON as the WebSocket frames.

| Method and path | Purpose |
|---|---|
| `POST /v1/workspaces/{workspace_id}/commands` | Submit one command; the response body is its `command_result`. |
| `GET /v1/workspaces/{workspace_id}/artifacts?kind=` | List current artifacts. |
| `GET /v1/workspaces/{workspace_id}/artifacts/{artifact_id}` | The current `Versioned` artifact. |
| `GET /v1/workspaces/{workspace_id}/artifacts/{artifact_id}/revisions` | Revision history. |
| `GET /v1/workspaces/{workspace_id}/events?after_seq=&thread_id=&limit=` | A page of the log, as envelopes. |
| `GET /v1/workspaces/{workspace_id}/threads/{thread_id}` | Thread metadata and focus. |

Rejections map to HTTP status codes: `version_conflict` → 409, `validation_failed` and `patch_failed` → 422, `not_found` → 404, `forbidden` → 403.

## MCP mapping

External agents connect over MCP with the same authority as any other actor.

| MCP | artifactr |
|---|---|
| Resource `artifact://{workspace_id}/{artifact_id}` | The current version: JSON, or Markdown for documents. The version number is in the resource metadata. |
| Resource template `artifact://{workspace_id}/{artifact_id}/revisions/{version}` | A past revision. |
| `subscriptions/listen` and resource-updated notifications | Driven by `artifact_changed` and `artifact_archived`, through a `SubscriptionBus` fed by the log. |
| Tools `list_artifacts`, `read_artifact`, `edit_document`, `edit_artifact`, `propose_edit`, `respond_to_proposal`, `post_message` | Commands, attributed to an `external_agent` actor for the MCP client. |

## Versioning and schema

- The protocol identifier is `artifactr.v1`. Within v1, changes are additive only: new optional fields and new event types. Clients must ignore unknown fields and keep unknown event types as opaque envelopes, since they still carry a `seq`.
- Breaking changes get a new subprotocol, `artifactr.v2`, served alongside v1 during migration.
- The JSON Schema for every frame is generated from the Pydantic models (`TypeAdapter(...).json_schema()`) into `schemas/artifactr.v1.json` and checked in. CI fails if it drifts. Clients generate their types from it, for example with `json-schema-to-typescript`.
