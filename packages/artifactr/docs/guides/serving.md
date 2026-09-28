# Serving over WebSocket and REST

`artifactr.fastapi` (the `fastapi` extra) serves workspaces to your frontend: the thread protocol over WebSocket, and REST endpoints for the same commands and for reads. Both are one FastAPI router, and both hand every command to `Runner.execute`, so a message or an edit behaves the same whichever way it arrives ([ADR-0012](../adr/0012-surfaces-websocket-rest-mcp.md), [ADR-0022](../adr/0022-surfaces-over-one-command-handler.md)). The wire format is specified in the [thread protocol](../protocol.md).

## Adding the router

```python
from fastapi import FastAPI
from starlette.requests import HTTPConnection

from artifactr import InMemoryStorage, Runner, UserActor, Workspaces
from artifactr.core import Actor, TenantId
from artifactr.fastapi import Unauthorized, artifactr_router

workspaces = Workspaces(InMemoryStorage(), types=[Plan, Brief])
runner = Runner(agent, app=None)


async def resolve_actor(connection: HTTPConnection) -> tuple[TenantId, Actor]:
    session = await sessions.load(connection.cookies.get("session"))  # your authentication
    if session is None:
        raise Unauthorized("sign in first")
    return session.tenant_id, UserActor(id=session.user_id, name=session.display_name)


app = FastAPI()
app.include_router(artifactr_router(workspaces, runner, resolve_actor=resolve_actor), prefix="/v1")
```

The router needs no lifespan of its own. Keep one `Workspaces` and one `Runner` per process: the runner owns the process's runs and their live output.

## Authentication and authorization

Authentication is your application's. `resolve_actor` receives the `HTTPConnection` of each REST request, and of each WebSocket before it is accepted, and returns the tenant and the actor. It can read headers, cookies or query parameters; browsers cannot set headers on a WebSocket, so a cookie or a short-lived token in the query string is usual there. Raise `Unauthorized` to refuse: REST answers 401, and the WebSocket is closed with code 4401.

The actor always comes from `resolve_actor`, never from the client's frames, so a client cannot act as someone else.

To decide which workspaces an actor may use, pass `authorize`:

```python
async def authorize(tenant_id: TenantId, workspace_id: str, actor: Actor) -> bool:
    return await memberships.exists(tenant_id, workspace_id, actor.id)


router = artifactr_router(workspaces, runner, resolve_actor=resolve_actor, authorize=authorize)
```

A refusal answers 403. Without `authorize`, any authenticated actor may use any workspace of its own tenant. [Multi-tenancy and security](security.md) covers the rest.

## REST

Every path is relative to the router's prefix, `/v1` above:

| Method and path | Purpose |
|---|---|
| `POST /workspaces/{workspace_id}/commands` | Submit one command frame; the response is its `command_result` |
| `GET /workspaces/{workspace_id}/artifacts?kind=&include_archived=` | List current artifacts |
| `GET /workspaces/{workspace_id}/artifacts/{artifact_id}` | One artifact's current version |
| `GET /workspaces/{workspace_id}/artifacts/{artifact_id}/revisions` | Its revisions, oldest first |
| `GET /workspaces/{workspace_id}/events?after_seq=&thread_id=&limit=` | A page of the log; `thread_id` may repeat |
| `GET /workspaces/{workspace_id}/threads` | Every thread |
| `GET /workspaces/{workspace_id}/threads/{thread_id}` | One thread, with its mode and focus |
| `GET /workspaces/{workspace_id}/proposals?status=` | Proposals, pending by default |
| `GET /workspaces/{workspace_id}/runs/{run_id}` | A run, with any requests it is paused on |

A command body is the same frame a WebSocket client sends:

```bash
curl -X POST localhost:8000/v1/workspaces/launch/commands \
  -H 'content-type: application/json' \
  -d '{"type": "command", "command_id": "c_1",
       "command": {"type": "post_message", "thread_id": "thr_1", "content": "Draft the plan"}}'
```

```json
{"type": "command_result", "command_id": "c_1", "ok": true, "outcome": {"seq": 12, "type": "recorded"}, "rejection": null}
```

A rejection answers with its status code (`STATUS_CODES`): 409 for `version_conflict` and `invalid_state`, 422 for `validation_failed` and `patch_failed`, 404 for `not_found` and 403 for `forbidden`. The body is still a `command_result`, with `ok: false` and the rejection's details.

`command_id` is chosen by the client and doubles as an idempotency key: the server remembers the most recent results (10,000 by default, per process), keyed by workspace, actor and `command_id`, and answers a repeated id with the original result instead of running the command twice. Retry a command that timed out with the same id.

## The WebSocket

A client connects to `/v1/workspaces/{workspace_id}/stream` with the subprotocol `artifactr.v1`, and sends `hello` with the last `seq` it has seen (0 the first time) and, optionally, the threads it follows:

```json
{"type": "hello", "protocol": "artifactr.v1", "resume_after_seq": 1041, "threads": ["thr_1"]}
```

The server answers `welcome`, with the log's head and the runs in progress, then replays every event after `resume_after_seq`, then sends `replay_complete`. From then on the client receives events as they commit, `command_result` frames for its commands, and live frames for runs in the threads it follows. It sends commands as command frames, and can attach to any run's live output with a `watch_run` command.

Replay and live delivery are one subscription to the log, so nothing falls between them. A client that reconnects says `hello` with its last `seq` and continues where it left off; if the server has lost events the client saw, `welcome` says `reset: true` and the client rebuilds from the replay.

The [thread protocol](../protocol.md) specifies every frame and close code, and [`schemas/artifactr.v1.json`](../reference/schema.md) gives the JSON Schema to generate client types from.

## Tuning

| `artifactr_router` option | Default | Meaning |
|---|---|---|
| `hello_timeout` | 10 seconds | How long a new connection has to send `hello` before it is closed (4408) |
| `outbox_size` | 1,000 frames | How far a connection may fall behind before it is closed (4429); it reconnects and resumes by `seq` |
| `remembered_commands` | 10,000 | Command results remembered for deduplication, per process |

Each connection reads frames in one task and runs each command as its own task, so a `stop_run` is never stuck behind a slow command. All outgoing frames go through one bounded outbox. A client too slow to keep up is disconnected rather than allowed to hold events back or grow the server's memory, and nothing is lost, because it resumes from the log.

## More than one process

The log, the proposals and the thread claims live in storage, so several server processes can serve one workspace once storage is shared. Two things are per process in v0.1: command deduplication, and runs with their live output (`stop_run` and `watch_run` reach only runs in the process that serves the request). Route a workspace's connections to one process, or accept those limits, until a shared channel exists ([open questions](../architecture.md#open-questions)).
