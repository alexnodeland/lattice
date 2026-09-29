"""The MCP server: external agents as workspace participants (ADR-0012)."""

import asyncio
import contextlib
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp.server.subscriptions import InMemorySubscriptionBus, ResourceUpdated, SubscriptionBus
from starlette.applications import Starlette

from artifactr.agent import (
    Runner,
    artifact_text,
    describe_outcome,
    list_artifacts_text,
    submit,
)
from artifactr.core import (
    ArtifactArchived,
    ArtifactChanged,
    ArtifactCreated,
    CreateArtifact,
    EditArtifact,
    ExternalAgentActor,
    FeedbackTarget,
    GiveFeedback,
    JsonPatch,
    Rejection,
    RespondToProposal,
    TenantId,
    WorkspaceId,
)
from artifactr.telemetry import annotate, attribution
from artifactr.workspace import Workspace, Workspaces

ResolveClient = Callable[[Context], Awaitable[tuple[TenantId, ExternalAgentActor]]]
"""Authenticates an MCP request: returns the client's tenant and actor."""

INSTRUCTIONS = (
    "This server is a shared workspace of artifacts that people and agents edit together. "
    "Read an artifact before changing it, prefer small precise edits, and pass the version "
    "you read so conflicting edits are caught. Some artifact types only accept proposals, "
    "which a person reviews."
)


def artifact_uri(tenant_id: TenantId, workspace_id: WorkspaceId, artifact_id: str) -> str:
    """Return an artifact's resource URI."""
    return f"artifactr://{tenant_id}/{workspace_id}/artifacts/{artifact_id}"


class ArtifactrMcp:
    """An MCP server over artifactr workspaces.

    Mount :meth:`http_app` in the application, and run :meth:`lifespan` in the application's
    lifespan. Every tool call goes through the same workspace and runner as the other surfaces,
    attributed to the client's :class:`~artifactr.core.ExternalAgentActor`.

    The MCP SDK traces each request itself, through the global tracer provider. The server adds
    the tenant, workspace and actor to those spans, and has no spans or metrics of its own.

    Args:
        workspaces: Opens tenant-scoped workspaces.
        runner: Carries out messages, so external agents can talk to the built-in agent.
        resolve: Authenticates each request.
        name: The server's name.
        bus: Where resource-change notifications go; in-process by default.
    """

    def __init__(
        self,
        workspaces: Workspaces,
        runner: Runner[Any],
        *,
        resolve: ResolveClient,
        name: str = "artifactr",
        bus: SubscriptionBus | None = None,
    ) -> None:
        self._workspaces = workspaces
        self._runner = runner
        self._resolve = resolve
        self._bus = bus or InMemorySubscriptionBus()
        self._watchers: dict[tuple[TenantId, WorkspaceId], asyncio.Task[None]] = {}
        self.server = MCPServer(name=name, instructions=INSTRUCTIONS, subscriptions=self._bus)
        self._register()

    def http_app(self, **options: Any) -> Starlette:
        """Return the Streamable HTTP app to mount, e.g. at ``/mcp``."""
        return self.server.streamable_http_app(**options)

    @contextlib.asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None]:
        """Run the HTTP session manager; stop watching workspaces afterwards."""
        async with self.server.session_manager.run():
            try:
                yield
            finally:
                await self.aclose()

    async def aclose(self) -> None:
        """Stop the tasks that turn workspace changes into resource notifications."""
        for task in self._watchers.values():
            task.cancel()
        await asyncio.gather(*self._watchers.values(), return_exceptions=True)
        self._watchers.clear()

    async def _open(self, ctx: Context, workspace_id: WorkspaceId) -> Workspace:
        tenant_id, actor = await self._resolve(ctx)
        annotate(attribution(tenant_id=tenant_id, workspace_id=workspace_id, actor=actor))
        workspace = await self._workspaces.open(tenant_id, workspace_id, actor=actor)
        key = (tenant_id, workspace_id)
        if key not in self._watchers:
            self._watchers[key] = asyncio.create_task(self._notify(tenant_id, workspace))
        return workspace

    async def _notify(self, tenant_id: TenantId, workspace: Workspace) -> None:
        head = await workspace.head_seq()
        async for envelope in workspace.subscribe(after_seq=head):
            event = envelope.event
            if isinstance(event, ArtifactCreated | ArtifactChanged | ArtifactArchived):
                uri = artifact_uri(tenant_id, workspace.workspace_id, event.artifact_id)
                await self._bus.publish(ResourceUpdated(uri=uri))

    def _register(self) -> None:
        server = self.server

        @server.tool()
        async def list_artifacts(workspace_id: str, ctx: Context, kind: str | None = None) -> str:
            """List a workspace's artifacts, optionally of one kind."""
            return await list_artifacts_text(await self._open(ctx, workspace_id), kind)

        @server.tool()
        async def read_artifact(workspace_id: str, artifact_id: str, ctx: Context) -> str:
            """Read an artifact's current version. Pass that version to edits."""
            workspace = await self._open(ctx, workspace_id)
            return await _tool(_read(workspace, artifact_id))

        @server.tool()
        async def create_artifact(
            workspace_id: str, kind: str, data: dict[str, Any], ctx: Context
        ) -> str:
            """Create an artifact of a kind the workspace accepts, from its JSON data."""
            workspace = await self._open(ctx, workspace_id)
            command = CreateArtifact(kind=kind, data=data)
            return describe_outcome(await _tool(workspace.commit(command)))

        @server.tool()
        async def edit_text(
            workspace_id: str,
            artifact_id: str,
            old: str,
            new: str,
            ctx: Context,
            base_version: int | None = None,
            field: str = "text",
            summary: str | None = None,
            propose: bool = False,
            rationale: str | None = None,
        ) -> str:
            """Replace the one exact occurrence of ``old`` in a text field with ``new``.

            Pass the ``base_version`` you read to fail rather than overwrite a newer change.
            """
            workspace = await self._open(ctx, workspace_id)
            artifact = await _tool(workspace.artifact(artifact_id))
            edit = artifact.edit_text(old, new, field=field, summary=summary)
            if base_version is not None:
                edit = edit.model_copy(update={"base_version": base_version})
            outcome = submit(workspace, edit, propose=propose, rationale=rationale)
            return describe_outcome(await _tool(outcome))

        @server.tool()
        async def edit_artifact(
            workspace_id: str,
            artifact_id: str,
            base_version: int,
            ops: list[dict[str, Any]],
            ctx: Context,
            summary: str | None = None,
            propose: bool = False,
            rationale: str | None = None,
        ) -> str:
            """Apply RFC 6902 JSON Patch operations to an artifact's data at ``base_version``."""
            workspace = await self._open(ctx, workspace_id)
            edit = EditArtifact(
                artifact_id=artifact_id,
                base_version=base_version,
                patch=JsonPatch(ops=tuple(ops)),
                summary=summary,
            )
            outcome = submit(workspace, edit, propose=propose, rationale=rationale)
            return describe_outcome(await _tool(outcome))

        @server.tool()
        async def archive_artifact(workspace_id: str, artifact_id: str, ctx: Context) -> str:
            """Archive an artifact that is no longer needed. It stays readable."""
            workspace = await self._open(ctx, workspace_id)
            artifact = await _tool(workspace.artifact(artifact_id))
            return describe_outcome(await _tool(workspace.commit(artifact.archive())))

        @server.tool()
        async def list_proposals(workspace_id: str, ctx: Context) -> str:
            """List the proposals awaiting review."""
            proposals = await (await self._open(ctx, workspace_id)).proposals()
            if not proposals:
                return "No proposals are awaiting review."
            return "\n".join(
                f"- {p.id}: {p.change.type} {p.artifact_id} by {p.proposed_by.display_name}"
                + (f" ({p.rationale})" if p.rationale else "")
                for p in proposals
            )

        @server.tool()
        async def respond_to_proposal(
            workspace_id: str,
            proposal_id: str,
            decision: Literal["accept", "reject"],
            ctx: Context,
            reason: str | None = None,
        ) -> str:
            """Accept or reject a proposal made by someone else."""
            workspace = await self._open(ctx, workspace_id)
            command = RespondToProposal(proposal_id=proposal_id, decision=decision, reason=reason)
            resolved = await _tool(workspace.commit(command))
            if resolved.version is None:
                return f"Rejected {proposal_id}."
            return f"Accepted {proposal_id}: the artifact is now at version {resolved.version}."

        @server.tool()
        async def give_feedback(
            workspace_id: str,
            feedback_type: str,
            target: FeedbackTarget,
            ctx: Context,
            value: dict[str, Any] | None = None,
        ) -> str:
            """Give feedback of an application-defined type on an artifact, thread, turn or message.

            ``value`` holds the feedback type's fields.
            """
            workspace = await self._open(ctx, workspace_id)
            command = GiveFeedback(feedback_type=feedback_type, target=target, value=value or {})
            await _tool(workspace.commit(command))
            return f"Recorded {feedback_type} feedback on the {target.kind}."

        @server.tool()
        async def post_message(
            workspace_id: str, thread_id: str, content: str, ctx: Context
        ) -> str:
            """Post a message in a thread. The thread's agent reads it and may reply."""
            workspace = await self._open(ctx, workspace_id)
            sent = await _tool(self._runner.send(workspace, thread_id, content))
            if sent.run is None:
                return "Posted; the agent already working in this thread will see it."
            return f"Posted; the agent started run {sent.run.run_id}."

        @server.resource(
            "artifactr://{tenant_id}/{workspace_id}/artifacts/{artifact_id}",
            mime_type="application/json",
            description="An artifact's current version, as JSON.",
        )
        async def artifact_resource(
            tenant_id: str, workspace_id: str, artifact_id: str, ctx: Context
        ) -> str:
            workspace = await self._resource_workspace(ctx, tenant_id, workspace_id)
            try:
                artifact = await workspace.artifact(artifact_id)
            except Rejection as rejection:
                raise ResourceError(rejection.message) from rejection
            return artifact.model_dump_json()

    async def _resource_workspace(
        self, ctx: Context, tenant_id: TenantId, workspace_id: WorkspaceId
    ) -> Workspace:
        resolved, _ = await self._resolve(ctx)
        if resolved != tenant_id:
            raise ResourceError(f"artifact resources of tenant {tenant_id} are not available")
        return await self._open(ctx, workspace_id)


async def _read(workspace: Workspace, artifact_id: str) -> str:
    return artifact_text(await workspace.artifact(artifact_id))


async def _tool[T](awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except Rejection as rejection:
        raise ToolError(rejection.message) from rejection
