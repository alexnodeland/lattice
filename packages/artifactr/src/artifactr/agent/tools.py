"""The generic tools every artifact-aware agent gets.

They cover what works for any artifact type: listing, reading, creating, editing text, and
archiving. Structured edits (adding a task to a plan) belong in the application's own tools,
which call ``ctx.deps.workspace.commit`` the same way.

Tools raise :class:`~artifactr.core.Rejection` as-is; :class:`ArtifactWorkspace` turns
rejections into retries with the rejection's message.
"""

import json
from collections.abc import Sequence
from typing import Any

from pydantic_ai import CallDeferred, FunctionToolset, RunContext

from artifactr.agent.session import Session
from artifactr.core import (
    Applied,
    ArchiveArtifact,
    Artifact,
    ArtifactId,
    CreateArtifact,
    EditArtifact,
    Outcome,
    ProposeChange,
    Proposed,
    Resolved,
    SetFocus,
    Versioned,
)
from artifactr.telemetry import annotate
from artifactr.telemetry.attributes import ARTIFACT_ID
from artifactr.workspace import Workspace

# Tools annotate their context as RunContext[...] literally: pydantic-ai detects context-taking
# tools by that annotation, and a type alias would hide it.
Context = RunContext[Session[Any]]


def artifact_tools(
    types: Sequence[type[Artifact]], *, ask: bool = False
) -> FunctionToolset[Session[Any]]:
    """Build the generic toolset for the given artifact types.

    Args:
        types: The artifact types the agent may create; their JSON Schemas are described to
            the model once, so tool definitions never change between requests.
        ask: Whether to include ``ask_user``, which pauses the run until someone answers.
            The agent's ``output_type`` must then include ``DeferredToolRequests``.
    """
    toolset = FunctionToolset[Session[Any]]()
    schemas = "\n".join(
        f"- {t.kind}: {json.dumps(t.model_json_schema(), separators=(',', ':'))}" for t in types
    )

    @toolset.tool
    async def list_artifacts(ctx: RunContext[Session[Any]], kind: str | None = None) -> str:
        """List the artifacts in the workspace, optionally of one kind.

        Args:
            kind: Only list artifacts of this kind.
        """
        return await list_artifacts_text(ctx.deps.workspace, kind)

    @toolset.tool
    async def read_artifact(ctx: RunContext[Session[Any]], artifact_id: str) -> str:
        """Read an artifact's current version. You will then be told when others change it.

        Args:
            artifact_id: The artifact to read.
        """
        artifact = await ctx.deps.workspace.artifact(artifact_id)
        await _follow(ctx, artifact.id)
        return artifact_text(artifact)

    @toolset.tool(
        description=f"Create an artifact of one of these kinds, whose data must match its "
        f"JSON Schema:\n{schemas}"
    )
    async def create_artifact(
        ctx: RunContext[Session[Any]], kind: str, data: dict[str, Any]
    ) -> str:
        command = CreateArtifact(kind=kind, data=data, thread_id=ctx.deps.thread_id)
        annotate({ARTIFACT_ID: command.artifact_id})  # the tool's span; it has no artifact_id
        outcome = await ctx.deps.workspace.commit(command)
        if isinstance(outcome, Applied):
            await _follow(ctx, outcome.artifact_id)
        return describe_outcome(outcome)

    @toolset.tool
    async def edit_text(
        ctx: RunContext[Session[Any]],
        artifact_id: str,
        old: str,
        new: str,
        field: str = "text",
        summary: str | None = None,
        propose: bool = False,
        rationale: str | None = None,
    ) -> str:
        """Replace one exact passage of an artifact's text field.

        Args:
            artifact_id: The artifact to edit.
            old: Text that occurs exactly once in the field now. Include enough context to make
                it unique. Use an empty string only to write into an empty field.
            new: The replacement text.
            field: The text field to edit.
            summary: A short description of the change, shown to others.
            propose: Propose the change for someone to review instead of applying it.
            rationale: Why you propose it; used with ``propose``.
        """
        artifact = await ctx.deps.workspace.artifact(artifact_id)
        edit = artifact.edit_text(
            old, new, field=field, summary=summary, thread_id=ctx.deps.thread_id
        )
        outcome = await submit(ctx.deps.workspace, edit, propose=propose, rationale=rationale)
        await _follow(ctx, artifact.id)
        return describe_outcome(outcome)

    @toolset.tool
    async def archive_artifact(ctx: RunContext[Session[Any]], artifact_id: str) -> str:
        """Archive an artifact that is no longer needed. It stays readable.

        Args:
            artifact_id: The artifact to archive.
        """
        artifact = await ctx.deps.workspace.artifact(artifact_id)
        command = artifact.archive(thread_id=ctx.deps.thread_id)
        return describe_outcome(await ctx.deps.workspace.commit(command))

    if ask:

        @toolset.tool_plain
        async def ask_user(question: str, choices: list[str] | None = None) -> str:
            """Ask the people in this thread a question and wait for the answer.

            Args:
                question: What you need to know.
                choices: Suggested answers, if the question has a few likely ones.
            """
            metadata = {"kind": "question", "question": question, "choices": choices}
            raise CallDeferred(metadata=metadata)

    return toolset


async def _follow(ctx: RunContext[Session[Any]], artifact_id: ArtifactId) -> None:
    """Add an artifact to the thread's focus, so the agent hears about changes to it."""
    workspace = ctx.deps.workspace
    thread = await workspace.thread(ctx.deps.thread_id)
    if artifact_id not in thread.focus:
        await workspace.commit(
            SetFocus(thread_id=thread.id, artifact_ids=(*thread.focus, artifact_id))
        )


async def list_artifacts_text(
    workspace: Workspace, kind: str | None = None, *, include_archived: bool = False
) -> str:
    """List a workspace's artifacts as text, one per line.

    Args:
        workspace: The workspace to list.
        kind: Only list artifacts of this kind.
        include_archived: List archived artifacts too, marked as archived.
    """
    artifacts = await workspace.artifacts(kind=kind, include_archived=include_archived)
    if not artifacts:
        return "There are no artifacts yet."
    return "\n".join(
        f"- {a.id} ({a.kind}, v{a.version}{', archived' if a.archived else ''})" for a in artifacts
    )


def artifact_text(artifact: Versioned[Artifact]) -> str:
    """Render an artifact for a model: a header line, then its ``render_for_agent`` text."""
    state = " (archived)" if artifact.archived else ""
    header = f"{artifact.id} ({artifact.kind}, v{artifact.version}){state}"
    return f"{header}\n\n{artifact.data.render_for_agent()}"


async def submit(
    workspace: Workspace,
    change: EditArtifact | ArchiveArtifact | CreateArtifact,
    *,
    propose: bool = False,
    rationale: str | None = None,
) -> Applied | Proposed:
    """Commit a change, or propose it for review when ``propose`` is set."""
    if propose:
        return await workspace.commit(ProposeChange(change=change, rationale=rationale))
    return await workspace.commit(change)


def describe_outcome(outcome: Outcome) -> str:
    """Tell a model what its command did, whatever the outcome."""
    match outcome:
        case Applied():
            return f"Done: {outcome.artifact_id} is now at version {outcome.version}."
        case Proposed():
            return (
                f"Proposed as {outcome.proposal_id}. A person will review it; you will be told "
                "whether it was accepted."
            )
        case Resolved(decision="reject"):
            return f"Rejected {outcome.proposal_id}."
        case Resolved():
            return (
                f"Accepted {outcome.proposal_id}: the artifact is now at version {outcome.version}."
            )
        case _:  # recorded: a command that changed no artifact
            return "Done."
