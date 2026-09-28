# External agents over MCP

Agents outside your application, such as a coding assistant, a desktop assistant or another service, can join a workspace over the [Model Context Protocol](https://modelcontextprotocol.io). `artifactr.mcp` (the `mcp` extra) serves one: artifacts are resources, commands are tools, and changes arrive as resource-updated notifications. An external agent is a participant like any other, with the same rules and the same attribution ([ADR-0012](../adr/0012-surfaces-websocket-rest-mcp.md)).

## Serving it

`ArtifactrMcp` wraps the MCP SDK's server. Mount its Streamable HTTP app in your application and run its lifespan inside the application's:

```python
import contextlib
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from mcp.server.mcpserver import Context

from artifactr.core import ExternalAgentActor, TenantId
from artifactr.mcp import ArtifactrMcp


async def resolve_client(ctx: Context) -> tuple[TenantId, ExternalAgentActor]:
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

Clients then connect to `https://your-host/mcp/` with any MCP client that speaks Streamable HTTP. `mcp.server` is the underlying `MCPServer`, if you need to serve it another way.

- **`resolve(ctx)`** authenticates each request and returns the client's tenant and its `ExternalAgentActor`. `ctx.headers` holds the HTTP request's headers. They are the client's own claims, so verify a credential rather than trusting a name.
- **`runner`** carries out messages, so an external agent can talk to the thread's built-in agent: its `post_message` starts, steers or answers a run like any other message.
- **`name`** is the server's name (`"artifactr"`), and **`bus`** is where resource notifications go (in-process by default).

## What a client sees

The server's instructions tell the client how to behave: read before changing, prefer small edits, pass the version it read, and expect some types to take proposals only.

| Tool | Does |
|---|---|
| `list_artifacts(workspace_id, kind=None)` | Lists the workspace's artifacts |
| `read_artifact(workspace_id, artifact_id)` | Reads an artifact's current version, rendered for agents |
| `create_artifact(workspace_id, kind, data)` | Creates an artifact of a type the workspace accepts |
| `edit_text(workspace_id, artifact_id, old, new, base_version=None, field="text", summary=None, propose=False, rationale=None)` | Replaces one exact passage of a text field |
| `edit_artifact(workspace_id, artifact_id, base_version, ops, summary=None, propose=False, rationale=None)` | Applies JSON Patch operations |
| `archive_artifact(workspace_id, artifact_id)` | Archives an artifact |
| `list_proposals(workspace_id)` | Lists the proposals awaiting review |
| `respond_to_proposal(workspace_id, proposal_id, decision, reason=None)` | Accepts or rejects someone else's proposal |
| `post_message(workspace_id, thread_id, content)` | Posts a message in a thread |

A rejection comes back as a tool error carrying its message, such as a version conflict telling the client to read again.

Each artifact is also a resource at `artifactr://{tenant_id}/{workspace_id}/artifacts/{artifact_id}`, whose content is the artifact's current version as JSON. A client may read resources of its own tenant only. Once a client has used a workspace, every change to its artifacts is published as a resource-updated notification for that URI, so subscribed clients know to read again. `artifact_uri(tenant_id, workspace_id, artifact_id)` builds the URI.

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
