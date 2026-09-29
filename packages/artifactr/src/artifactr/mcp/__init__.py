"""artifactr workspaces over the Model Context Protocol.

External agents (coding assistants, desktop assistants, other services) connect as MCP
clients and work in a workspace like any other participant: artifacts are resources, commands
are tools, and changes arrive as resource-updated notifications::

    mcp = ArtifactrMcp(workspaces, runner, resolve=resolve_client)
    app.mount("/mcp", mcp.http_app(streamable_http_path="/"))
    # and in the application's lifespan:
    async with mcp.lifespan():
        yield
"""

from artifactr.mcp.server import INSTRUCTIONS, ArtifactrMcp, McpContext, ResolveClient, artifact_uri

__all__ = ["INSTRUCTIONS", "ArtifactrMcp", "McpContext", "ResolveClient", "artifact_uri"]
