# External agents over MCP

Agents outside your application, such as a coding assistant, a desktop assistant or another service, can join a workspace over the [Model Context Protocol](https://modelcontextprotocol.io). `artifactr.mcp` (the `mcp` extra) serves one: artifacts are resources, commands are tools, and changes arrive as resource-updated notifications. An external agent is a participant like any other, with the same rules and the same attribution ([ADR-0048](../adr/0048-surfaces-over-the-runner.md)).

## Serving it

`ArtifactrMcp` wraps the MCP SDK's server. Mount its Streamable HTTP app in your application and run its lifespan inside the application's:

```python
import contextlib
from collections.abc import AsyncGenerator

from fastapi import FastAPI

from artifactr.core import ExternalAgentActor, TenantId
from artifactr.mcp import ArtifactrMcp, McpContext


async def resolve_client(ctx: McpContext) -> tuple[TenantId, ExternalAgentActor]:
    client = await api_keys.verify((ctx.headers or {}).get("authorization"))  # your authentication
    return client.tenant_id, ExternalAgentActor(client_id=client.id, name=client.name)


mcp = ArtifactrMcp(workspaces, runner, resolve=resolve_client)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    async with mcp.lifespan():
        yield


app = FastAPI(lifespan=lifespan)
app.mount("/mcp", mcp.http_app(streamable_http_path="/"))
```

Clients then connect to `https://your-host/mcp/` with any MCP client that speaks Streamable HTTP. `mcp.server` is the underlying `MCPServer`, if you need to serve it another way. The SDK's server configures logging for the whole process as it is built, and `ArtifactrMcp` undoes that, so logging stays the application's ([Logging and startup output](serving.md#logging-and-startup-output)).

- **`resolve(ctx)`** authenticates each request and returns the client's tenant and its `ExternalAgentActor`. `ctx.headers` holds the HTTP request's headers. They are the client's own claims, so verify a credential rather than trusting a name. `ctx` is an `McpContext`, the MCP SDK's `Context` with its request typed. Over HTTP, `ctx.request_context.request` is the Starlette `Request`, so an authenticator written for the router's `resolve_actor` can take it without a cast. Check it for `None` first: the in-process client that tests use has no HTTP request.

  ```python
  from mcp.server.mcpserver.exceptions import ToolError

  from artifactr.core import UserActor


  async def resolve_client(ctx: McpContext) -> tuple[TenantId, ExternalAgentActor]:
      request = ctx.request_context.request  # a starlette Request, or None
      if request is None:
          raise ToolError("connect over HTTP")
      user = await authenticate(request)  # the function resolve_actor uses
      return user.tenant_id, ExternalAgentActor(
          client_id=user.id,
          name=f"{user.name} (MCP)",
          on_behalf_of=UserActor(id=user.id, name=user.name),
      )
  ```

  A client a person connects with their own token acts for them: set `on_behalf_of`, so checks, and the proposal rule, see the person. Leave it empty for a client with credentials of its own.

- **`runner`** carries out every tool's command, so an external agent can talk to the thread's built-in agent: its `post_message` starts, steers or answers a run like any other message. The runner also remembers commands' results, so a retried tool call with a `command_id` is carried out once ([Retries](#retries)).
- **`name`** is the server's name (`"artifactr"`), and **`bus`** is where resource notifications go (in-process by default).

## Authorization

The `authorize` hook `Workspaces` holds decides what a client may do, as it does for the router ([Authentication and authorization](serving.md#authentication-and-authorization)); the server takes no hook of its own ([ADR-0056](../adr/0056-access-asked-in-every-workspace-method.md)). Each tool calls `Workspace` methods, and each method asks the hook first, so a tool call is asked for opening the workspace (`artifactr:open`) and for each action it takes: `edit_text` for reading the artifact and editing it, `list_threads` for `artifactr:read_threads`. `list_workspaces` names no workspace: it is asked for `artifactr:read_workspaces`, then for opening each workspace it finds, and lists those allowed. A resource read is asked for `artifactr:read_artifacts`, and so is each artifact a `subscriptions/listen` request names, when the stream opens.

A refusal is a tool error carrying the message of REST's 403, such as `Error executing tool list_artifacts: artifactr:open is refused in this workspace`. A refused resource read fails with the same message, and so does a `subscriptions/listen` request that names a refused artifact ([Resources](#resources)). Listing the tools and the resource template names no workspace, so neither is asked. Without `authorize`, a client may do anything in every workspace of the tenant `resolve` returns.

## What a client sees

The server's instructions tell the client how to behave: read before changing, prefer small edits, pass the version it read, expect some types to take proposals only, and give each change a `command_id`.

The tools that change something:

| Tool | Does |
|---|---|
| `create_artifact(workspace_id, kind, data)` | Creates an artifact of a type the workspace accepts |
| `edit_text(workspace_id, artifact_id, old, new, base_version=None, field="text", summary=None, propose=False, rationale=None)` | Replaces one exact passage of a text field |
| `edit_artifact(workspace_id, artifact_id, base_version, ops, summary=None, propose=False, rationale=None)` | Applies JSON Patch operations |
| `archive_artifact(workspace_id, artifact_id)` | Archives an artifact |
| `respond_to_proposal(workspace_id, proposal_id, decision, reason=None)` | Accepts or rejects someone else's proposal |
| `post_message(workspace_id, thread_id, content, kind="message")` | Posts a message in a thread, and says which run it started; a `notice` is for people, and starts no run |
| `give_feedback(workspace_id, feedback_type, target, value=None)` | Gives feedback of an application's type on an artifact, thread, turn or message |

Each also takes an optional `command_id` ([Retries](#retries)). The reads cover [REST](serving.md#rest)'s reads of workspaces, artifacts, revisions, proposals, threads, runs and the log:

| Tool | Returns |
|---|---|
| `list_workspaces(after=None, limit=100)` | The workspaces of the client's tenant that it may open, one id per line, as `GET /v1/workspaces` lists them |
| `list_artifacts(workspace_id, kind=None, include_archived=False)` | The workspace's artifacts, one per line, archived ones marked |
| `read_artifact(workspace_id, artifact_id)` | An artifact's current version, rendered for agents |
| `list_revisions(workspace_id, artifact_id)` | An artifact's revisions, oldest first, as JSON lines |
| `list_proposals(workspace_id, status="pending")` | Proposals with a status (`pending`, `accepted` or `rejected`), or all of them with `null` |
| `list_threads(workspace_id)` | The workspace's threads, oldest first, as JSON lines |
| `get_thread(workspace_id, thread_id)` | A thread, with its mode and focus, as JSON |
| `get_run(workspace_id, run_id)` | A run, with any requests it is paused on, as JSON |
| `read_events(workspace_id, after_seq=0, before_seq=None, threads=None, limit=None, last=None)` | Envelopes of the log, oldest first, as JSON lines, as `GET /v1/workspaces/{workspace_id}/events` reads them: the window `after_seq < seq < before_seq`, for `threads`, the first `limit` or the last `last`. Without either, the first 50. To read back from the latest events, give `last`, then `before_seq` the oldest `seq` returned |

The JSON is what the REST endpoint returns. A rejection comes back as a tool error carrying its message, such as a version conflict telling the client to read again.

## Retries

Agents retry tool calls, and transports drop replies. Give each call that changes something a `command_id` of the client's choosing, and the same id when retrying it: the server carries the command out once, and answers the retry with the first result, including a rejection. It is the `command_id` of REST's command frames, and one memory serves every surface, keyed by the tenant, the workspace, the client and the id ([Deduplication](../protocol.md#deduplication)). A call without a `command_id` is carried out every time.

```python
message = {"workspace_id": "launch", "thread_id": "thr_1", "content": "Draft the plan"}
first = await client.call_tool("post_message", {**message, "command_id": "c_7"})
again = await client.call_tool("post_message", {**message, "command_id": "c_7"})  # posted once
```

`post_message` says which run the message started, so the client can follow it with `get_run`.

## Resources

Each artifact is also a resource at `artifactr://{tenant_id}/{workspace_id}/artifacts/{artifact_id}`, whose content is the artifact's current version as JSON. A client may read, and subscribe to, the artifacts of its own tenant only, that `authorize` lets it read. Once a client has used a workspace, every change to its artifacts is published as a resource-updated notification for that URI, so subscribed clients know to read again. `artifact_uri(tenant_id, workspace_id, artifact_id)` builds the URI.

A read the server refuses (an artifact that does not exist, another tenant's, or one `authorize` refuses) fails with the JSON-RPC error `INVALID_PARAMS`, as the MCP SDK reports a missing resource. The error's `data` holds the `uri` and the `rejection` as REST reports it, whose `type` is `not_found` or `forbidden`. A `subscriptions/listen` request that names such an artifact fails the same way. `INTERNAL_ERROR` means the server itself failed.

## Rules for external agents

External agents are agents: write policies bind them, so a change to a `"propose"` type becomes a proposal, exactly as for the built-in agent. Their actions are attributed to their `ExternalAgentActor`, so people, the built-in agent and other clients see who changed what. They cannot answer their own proposals, and they do not record facts about the built-in agent's runs.

## Trying it

The MCP SDK's client can connect in-process, which is also how the library's own tests exercise the server:

```python
from mcp import Client

async with Client(mcp.server) as client:
    result = await client.call_tool("list_artifacts", {"workspace_id": "launch"})
    print(result.content[0].text)
```

The [reference implementation](../reference-implementation.md) serves MCP at `/mcp` next to its WebSocket and REST endpoints.
