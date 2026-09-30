"""The MCP server: external agents as workspace participants (ADR-0048)."""

import asyncio
import contextlib
import logging
import re
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator, Sequence
from typing import Annotated, Any, Literal

from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.subscriptions import InMemorySubscriptionBus, ResourceUpdated, SubscriptionBus
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS, SubscriptionsListenRequestParams
from pydantic import BaseModel, Field
from starlette.applications import Starlette
from starlette.requests import Request

from artifactr.agent import Runner, artifact_text, describe_outcome, list_artifacts_text
from artifactr.core import (
    ArtifactArchived,
    ArtifactChanged,
    ArtifactCreated,
    Command,
    CreateArtifact,
    EditArtifact,
    ExternalAgentActor,
    FeedbackTarget,
    Forbidden,
    GiveFeedback,
    JsonPatch,
    Outcome,
    PostMessage,
    ProposeChange,
    Recorded,
    Rejection,
    RespondToProposal,
    TenantId,
    WorkspaceId,
    new_id,
)
from artifactr.telemetry import annotate, attribution
from artifactr.workspace import Authorize, Workspace, Workspaces

type McpContext = Context[Any, Request]
"""The context a :data:`ResolveClient` receives: the MCP SDK's ``Context`` of one request.

Over HTTP, ``ctx.request_context.request`` is the Starlette ``Request`` the call arrived in, so
an authenticator written for the router's ``HTTPConnection`` can take it once it is checked
for ``None``, which it is in process, as in tests. ``ctx.headers`` holds its headers.
"""

ResolveClient = Callable[[McpContext], Awaitable[tuple[TenantId, ExternalAgentActor]]]
"""Authenticates an MCP request: returns the client's tenant and actor."""

INSTRUCTIONS = (
    "This server is a shared workspace of artifacts that people and agents edit together. "
    "Read an artifact before changing it, prefer small precise edits, and pass the version "
    "you read so conflicting edits are caught. Some artifact types only accept proposals, "
    "which a person reviews. Give each change a command_id of your own, and the same one if "
    "you retry it, so that it is made once."
)

_CommandId = Annotated[
    str | None,
    Field(
        description="An id of your choosing for this change. A retry with the same id returns "
        "the first result instead of making the change again."
    ),
]
"""A command tool's optional ``command_id``: the idempotency key of REST's command frames."""


_READ_LIMIT = 50
"""How many envelopes ``read_events`` returns when it is given neither ``limit`` nor ``last``."""

_NO_PROPOSALS = {
    "pending": "No proposals are awaiting review.",
    "accepted": "No proposals have been accepted.",
    "rejected": "No proposals have been rejected.",
    None: "No proposals have been made.",
}

_ARTIFACT_URI = re.compile(r"artifactr://(?P<tenant>[^/]+)/(?P<workspace>[^/]+)/artifacts/[^/]+")


def artifact_uri(tenant_id: TenantId, workspace_id: WorkspaceId, artifact_id: str) -> str:
    """Return an artifact's resource URI."""
    return f"artifactr://{tenant_id}/{workspace_id}/artifacts/{artifact_id}"


@contextlib.contextmanager
def _logging_left_alone() -> Generator[None]:
    """Put the root logger's handlers and level back as they were when the block ends.

    The MCP SDK's ``MCPServer`` calls ``logging.basicConfig`` as it is built, which has no
    option to skip it: if the root logger has no handlers yet, the whole process then logs at
    INFO through a rich handler. Logging is the application's to configure, so the handlers the
    block added are removed and closed, and the level restored.

    Shared verbatim with reflexr's ``src/reflexr/mcp/server.py``; change both.
    """
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    try:
        yield
    finally:
        for added in [handler for handler in root.handlers if handler not in handlers]:
            root.removeHandler(added)
            added.close()
        root.setLevel(level)


class ArtifactrMcp:
    """An MCP server over artifactr workspaces.

    Mount :meth:`http_app` in the application, and run :meth:`lifespan` in the application's
    lifespan. Every tool call goes through the same workspace and runner as the other surfaces,
    attributed to the client's :class:`~artifactr.core.ExternalAgentActor`.

    The MCP SDK traces each request itself, through the global tracer provider. The server adds
    the tenant, workspace and actor to those spans, and has no spans or metrics of its own.
    Building the SDK's server configures logging for the whole process; this server undoes
    that, so logging stays the application's.

    Args:
        workspaces: Opens tenant-scoped workspaces.
        runner: Carries out every tool's command, once per ``command_id``, so a message reaches
            the thread's agent and a retry is safe, as on REST.
        resolve: Authenticates each request.
        authorize: Whether a client may use a workspace of its tenant: the router's hook, asked
            on every tool call, resource read and resource subscription that names a workspace;
            allows everything if omitted. A refusal is a tool error, or a resource read or
            subscription failing with ``INVALID_PARAMS``, carrying the ``forbidden`` rejection's
            message.
        name: The server's name.
        bus: Where resource-change notifications go; in-process by default.
    """

    def __init__(
        self,
        workspaces: Workspaces,
        runner: Runner[Any],
        *,
        resolve: ResolveClient,
        authorize: Authorize | None = None,
        name: str = "artifactr",
        bus: SubscriptionBus | None = None,
    ) -> None:
        self._workspaces = workspaces
        self._runner = runner
        self._resolve = resolve
        self._authorize = authorize
        self._bus = bus or InMemorySubscriptionBus()
        self._watchers: dict[tuple[TenantId, WorkspaceId], asyncio.Task[None]] = {}
        with _logging_left_alone():
            self.server = MCPServer(
                name=name,
                instructions=INSTRUCTIONS,
                subscriptions=self._bus,
                middleware=[self._check_subscriptions],
            )
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

    async def _open(
        self,
        ctx: Context,
        workspace_id: WorkspaceId,
        client: tuple[TenantId, ExternalAgentActor] | None = None,
    ) -> Workspace:
        """Open a workspace for the request's client, resolving it unless it is given.

        Raises:
            Forbidden: If ``authorize`` refuses the client this workspace.
        """
        tenant_id, actor = client or await self._resolve(ctx)
        annotate(attribution(tenant_id=tenant_id, workspace_id=workspace_id, actor=actor))
        workspace = await self._workspaces.open(
            tenant_id, workspace_id, actor=actor, authorize=self._authorize
        )
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

    async def _workspace(self, ctx: Context, workspace_id: WorkspaceId) -> Workspace:
        """Open a workspace for a tool, whose refusal is a tool error."""
        return await _tool(self._open(ctx, workspace_id))

    async def _outcome(
        self, workspace: Workspace, command: Command, command_id: str | None
    ) -> Outcome:
        """Carry out a tool's command through the runner, once per ``command_id``.

        A command without one gets a new id, so it is carried out, and remembered, like any.

        Raises:
            ToolError: If the command is rejected, now or when it was first carried out.
        """
        if command_id is None:
            command_id = new_id("cmd")
        result = await self._runner.execute(workspace, command, command_id=command_id)
        if result.outcome is None:
            raise ToolError(str((result.rejection or {}).get("message")))
        return result.outcome

    async def _check_subscriptions(
        self, ctx: ServerRequestContext[Any, Any], call_next: CallNext
    ) -> HandlerResult:
        """Check a subscription to artifacts as a read of them is checked.

        The MCP SDK serves ``subscriptions/listen`` itself, so this middleware asks, when a
        stream opens, what reading each artifact it names would: its tenant, and ``authorize``.
        A refusal fails the request, with the resource read's message.
        """
        if ctx.method == "subscriptions/listen":
            params = SubscriptionsListenRequestParams.model_validate(ctx.params, by_name=False)
            await self._check_uris(ctx, params.notifications.resource_subscriptions or ())
        return await call_next(ctx)

    async def _check_uris(self, ctx: ServerRequestContext[Any, Any], uris: Sequence[str]) -> None:
        scopes: dict[tuple[str, str], str] = {}
        for uri in uris:
            if (match := _ARTIFACT_URI.fullmatch(uri)) is not None:
                scopes.setdefault((match["tenant"], match["workspace"]), uri)
        if not scopes:
            return  # no artifact, so nothing of a workspace's to refuse
        context = Context(request_context=ctx, mcp_server=self.server, subscriptions=self._bus)
        tenant_id, actor = await self._resolve(context)
        for (tenant, workspace_id), uri in scopes.items():
            if tenant != tenant_id:
                raise _refused(uri, Forbidden(_unavailable(tenant)))
            try:
                await self._workspaces.open(
                    tenant_id, workspace_id, actor=actor, authorize=self._authorize
                )
            except Forbidden as refused:
                raise _refused(uri, refused) from refused

    def _register(self) -> None:
        server = self.server

        @server.tool()
        async def list_artifacts(
            workspace_id: str, ctx: Context, kind: str | None = None, include_archived: bool = False
        ) -> str:
            """List a workspace's artifacts, optionally of one kind, and archived ones too."""
            workspace = await self._workspace(ctx, workspace_id)
            return await list_artifacts_text(workspace, kind, include_archived=include_archived)

        @server.tool()
        async def read_artifact(workspace_id: str, artifact_id: str, ctx: Context) -> str:
            """Read an artifact's current version. Pass that version to edits."""
            workspace = await self._workspace(ctx, workspace_id)
            return await _tool(_read(workspace, artifact_id))

        @server.tool()
        async def list_revisions(workspace_id: str, artifact_id: str, ctx: Context) -> str:
            """List an artifact's revisions, oldest first, as JSON lines.

            Each has its version, its data, the patch that made it and who made it.
            """
            workspace = await self._workspace(ctx, workspace_id)
            return _json_lines(await _tool(workspace.revisions(artifact_id)))

        @server.tool()
        async def create_artifact(
            workspace_id: str,
            kind: str,
            data: dict[str, Any],
            ctx: Context,
            command_id: _CommandId = None,
        ) -> str:
            """Create an artifact of a kind the workspace accepts, from its JSON data."""
            workspace = await self._workspace(ctx, workspace_id)
            command = CreateArtifact(kind=kind, data=data)
            return describe_outcome(await self._outcome(workspace, command, command_id))

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
            command_id: _CommandId = None,
        ) -> str:
            """Replace the one exact occurrence of ``old`` in a text field with ``new``.

            Pass the ``base_version`` you read to fail rather than overwrite a newer change.
            """
            workspace = await self._workspace(ctx, workspace_id)
            artifact = await _tool(workspace.artifact(artifact_id))
            edit = artifact.edit_text(old, new, field=field, summary=summary)
            if base_version is not None:
                edit = edit.model_copy(update={"base_version": base_version})
            command = ProposeChange(change=edit, rationale=rationale) if propose else edit
            return describe_outcome(await self._outcome(workspace, command, command_id))

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
            command_id: _CommandId = None,
        ) -> str:
            """Apply RFC 6902 JSON Patch operations to an artifact's data at ``base_version``."""
            workspace = await self._workspace(ctx, workspace_id)
            edit = EditArtifact(
                artifact_id=artifact_id,
                base_version=base_version,
                patch=JsonPatch(ops=tuple(ops)),
                summary=summary,
            )
            command = ProposeChange(change=edit, rationale=rationale) if propose else edit
            return describe_outcome(await self._outcome(workspace, command, command_id))

        @server.tool()
        async def archive_artifact(
            workspace_id: str, artifact_id: str, ctx: Context, command_id: _CommandId = None
        ) -> str:
            """Archive an artifact that is no longer needed. It stays readable."""
            workspace = await self._workspace(ctx, workspace_id)
            artifact = await _tool(workspace.artifact(artifact_id))
            outcome = await self._outcome(workspace, artifact.archive(), command_id)
            return describe_outcome(outcome)

        @server.tool()
        async def list_proposals(
            workspace_id: str,
            ctx: Context,
            status: Literal["pending", "accepted", "rejected"] | None = "pending",
        ) -> str:
            """List proposals with a status, pending by default; ``null`` lists them all."""
            workspace = await self._workspace(ctx, workspace_id)
            proposals = await workspace.proposals(status=status)
            if not proposals:
                return _NO_PROPOSALS[status]
            return "\n".join(
                f"- {p.id}: {p.change.type} {p.artifact_id} by {p.proposed_by.display_name}, "
                f"{p.status}" + (f" ({p.rationale})" if p.rationale else "")
                for p in proposals
            )

        @server.tool()
        async def respond_to_proposal(
            workspace_id: str,
            proposal_id: str,
            decision: Literal["accept", "reject"],
            ctx: Context,
            reason: str | None = None,
            command_id: _CommandId = None,
        ) -> str:
            """Accept or reject a proposal made by someone else."""
            workspace = await self._workspace(ctx, workspace_id)
            command = RespondToProposal(proposal_id=proposal_id, decision=decision, reason=reason)
            return describe_outcome(await self._outcome(workspace, command, command_id))

        @server.tool()
        async def give_feedback(
            workspace_id: str,
            feedback_type: str,
            target: FeedbackTarget,
            ctx: Context,
            value: dict[str, Any] | None = None,
            command_id: _CommandId = None,
        ) -> str:
            """Give feedback of an application-defined type on an artifact, thread, turn or message.

            ``value`` holds the feedback type's fields.
            """
            workspace = await self._workspace(ctx, workspace_id)
            command = GiveFeedback(feedback_type=feedback_type, target=target, value=value or {})
            await self._outcome(workspace, command, command_id)
            return f"Recorded {feedback_type} feedback on the {target.kind}."

        @server.tool()
        async def list_threads(workspace_id: str, ctx: Context) -> str:
            """List the workspace's threads, oldest first, as JSON lines."""
            threads = await (await self._workspace(ctx, workspace_id)).threads()
            return _json_lines(threads) or "There are no threads yet."

        @server.tool()
        async def get_thread(workspace_id: str, thread_id: str, ctx: Context) -> str:
            """Return a thread as JSON: its title, its mode, and the artifacts it follows."""
            workspace = await self._workspace(ctx, workspace_id)
            return (await _tool(workspace.thread(thread_id))).model_dump_json()

        @server.tool()
        async def post_message(
            workspace_id: str,
            thread_id: str,
            content: str,
            ctx: Context,
            command_id: _CommandId = None,
        ) -> str:
            """Post a message in a thread. The thread's agent reads it and may reply."""
            workspace = await self._workspace(ctx, workspace_id)
            command = PostMessage(thread_id=thread_id, content=content)
            outcome = await self._outcome(workspace, command, command_id)
            run_id = outcome.run_id if isinstance(outcome, Recorded) else None
            if run_id is None:
                return "Posted; the agent already working in this thread will see it."
            return f"Posted; the agent started run {run_id}."

        @server.tool()
        async def get_run(workspace_id: str, run_id: str, ctx: Context) -> str:
            """Return a run as JSON: its status, and any requests it is paused on."""
            workspace = await self._workspace(ctx, workspace_id)
            return (await _tool(workspace.run(run_id))).model_dump_json()

        @server.tool()
        async def read_events(
            workspace_id: str,
            ctx: Context,
            after_seq: int = 0,
            before_seq: int | None = None,
            threads: list[str] | None = None,
            limit: int | None = None,
            last: int | None = None,
        ) -> str:
            """Read envelopes from a workspace's log, oldest first, as JSON lines.

            The window is ``after_seq < seq < before_seq``. ``threads`` keeps those threads'
            events and every artifact and proposal event. ``limit`` reads the window's first
            envelopes and ``last`` its last ones; without either, the first 50. To read back
            through the log, give ``last``, then ``before_seq`` the oldest ``seq`` returned.
            """
            workspace = await self._workspace(ctx, workspace_id)
            if limit is None and last is None:
                limit = _READ_LIMIT
            found = await _tool(
                workspace.read(
                    after_seq=after_seq,
                    before_seq=before_seq,
                    threads=threads,
                    limit=limit,
                    last=last,
                )
            )
            return _json_lines(found) or "No events."

        @server.resource(
            "artifactr://{tenant_id}/{workspace_id}/artifacts/{artifact_id}",
            mime_type="application/json",
            description="An artifact's current version, as JSON.",
        )
        async def artifact_resource(
            tenant_id: str, workspace_id: str, artifact_id: str, ctx: Context
        ) -> str:
            try:
                resolved, actor = await self._resolve(ctx)
                if resolved != tenant_id:
                    raise Forbidden(_unavailable(tenant_id))
                workspace = await self._open(ctx, workspace_id, (resolved, actor))
                artifact = await workspace.artifact(artifact_id)
            except Rejection as rejection:
                uri = artifact_uri(tenant_id, workspace_id, artifact_id)
                raise _refused(uri, rejection) from rejection
            return artifact.model_dump_json()


def _unavailable(tenant_id: TenantId) -> str:
    return f"artifact resources of tenant {tenant_id} are not available"


def _refused(uri: str, rejection: Rejection) -> MCPError:
    """A resource read or subscription the server refuses, as the protocol error to raise.

    It is ``INVALID_PARAMS``, as the SDK reports a missing resource, so clients can tell a
    refusal from a failure of the server (``INTERNAL_ERROR``). Its data carries the URI and
    the rejection, as REST's error body does.
    """
    data = {"uri": uri, "rejection": rejection.payload()}
    return MCPError(INVALID_PARAMS, rejection.message, data=data)


def _json_lines(models: Sequence[BaseModel]) -> str:
    return "\n".join(model.model_dump_json() for model in models)


async def _read(workspace: Workspace, artifact_id: str) -> str:
    return artifact_text(await workspace.artifact(artifact_id))


async def _tool[T](awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except Rejection as rejection:
        raise ToolError(rejection.message) from rejection
