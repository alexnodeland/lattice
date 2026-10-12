"""The tools [`ArtifactrCapability`][relayr.outbound.ArtifactrCapability] gives an agent."""

import json
from typing import Any

from pydantic import JsonValue
from pydantic_ai import FunctionToolset, ModelRetry, RunContext

import artifactr.core as a
from reflexr.workspace import Reaction
from relayr.outbound.actions import NotAllowed, Outbound, Refused

# Tools annotate their context as RunContext[...] literally: pydantic-ai detects context-taking
# tools by that annotation, and a type alias would hide it.


def artifactr_tools(outbound: Outbound) -> FunctionToolset[Reaction[Any]]:
    """Build the tools for acting in artifactr through `outbound`."""
    toolset = FunctionToolset[Reaction[Any]]()

    @toolset.tool
    async def read_artifact(ctx: RunContext[Reaction[Any]], artifact_id: str) -> str:
        """Read an artifact's current version: its kind, version and data, as JSON.

        Args:
            artifact_id: The artifact.
        """
        try:
            current = await outbound.acting(ctx.deps).read(artifact_id)
        except Refused as refused:
            raise ModelRetry(str(refused)) from refused
        data = current.data.to_json()
        return json.dumps({"kind": current.data.kind, "version": current.version, "data": data})

    @toolset.tool
    async def create_artifact(
        ctx: RunContext[Reaction[Any]],
        kind: str,
        data: dict[str, JsonValue],
        thread_id: str | None = None,
        rationale: str | None = None,
    ) -> str:
        """Create an artifact, as a proposal unless your rule may create its kind directly.

        Args:
            kind: The artifact's kind.
            data: Its data.
            thread_id: The thread it is made from; by default the one that fired the rule.
            rationale: Why, for the people who review the proposal.
        """
        try:
            artifact = a.load_artifact(kind, data)
            acting = outbound.acting(ctx.deps)
            return await acting.create(artifact, thread_id=thread_id, rationale=rationale)
        except (NotAllowed, Refused, a.Rejection) as refused:
            raise ModelRetry(str(refused)) from refused

    @toolset.tool
    async def edit_artifact(
        ctx: RunContext[Reaction[Any]],
        artifact_id: str,
        path: str,
        value: JsonValue,
        summary: str | None = None,
        thread_id: str | None = None,
        rationale: str | None = None,
    ) -> str:
        """Set one value in an artifact, as a proposal unless your rule may edit its kind.

        Args:
            artifact_id: The artifact.
            path: Where, as a JSON Pointer, such as `/entries/deploy-42`.
            value: The value to set there.
            summary: What the change does.
            thread_id: The thread it is made from; by default the one that fired the rule.
            rationale: Why, for the people who review the proposal.
        """
        try:
            acting = outbound.acting(ctx.deps)
            await acting.edit(
                artifact_id,
                path,
                value,
                summary=summary,
                thread_id=thread_id,
                rationale=rationale,
            )
        except (NotAllowed, Refused) as refused:
            raise ModelRetry(str(refused)) from refused
        return "Done."

    @toolset.tool
    async def post_notice(
        ctx: RunContext[Reaction[Any]], content: str, thread_id: str | None = None
    ) -> str:
        """Post a notice in a thread, for people: it starts no turn of the assistant.

        Args:
            content: What it says.
            thread_id: Where; by default the thread that fired the rule.
        """
        try:
            return await outbound.acting(ctx.deps).notice(content, thread_id=thread_id)
        except (NotAllowed, Refused) as refused:
            raise ModelRetry(str(refused)) from refused

    @toolset.tool
    async def create_thread(ctx: RunContext[Reaction[Any]], title: str) -> str:
        """Create a thread, if your rule may, and return its id.

        Args:
            title: Its title.
        """
        try:
            return await outbound.acting(ctx.deps).create_thread(title)
        except (NotAllowed, Refused) as refused:
            raise ModelRetry(str(refused)) from refused

    @toolset.tool
    async def send_message(
        ctx: RunContext[Reaction[Any]], content: str, thread_id: str | None = None
    ) -> str:
        """Send a message that starts the assistant's next turn in a thread, if your rule may.

        Args:
            content: What it says.
            thread_id: Where; by default the thread that fired the rule.
        """
        try:
            return await outbound.acting(ctx.deps).send(content, thread_id=thread_id)
        except (NotAllowed, Refused) as refused:
            raise ModelRetry(str(refused)) from refused

    return toolset
