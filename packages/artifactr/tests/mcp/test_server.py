"""External agents over MCP: tools, resources and change notifications."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
from mcp import Client
from mcp.server.mcpserver import Context
from mcp.server.subscriptions import ResourceUpdated
from mcp.shared.exceptions import MCPError

import tests.artifact_types  # noqa: F401  (registers the test artifact types)
from artifactr.core import ExternalAgentActor, TenantId, UserActor
from artifactr.mcp import ArtifactrMcp, artifact_uri
from artifactr.workspace import InMemoryStorage, Workspace, Workspaces
from tests.agent.conftest import Gate, Script, call, make_agent, say
from tests.artifact_types import Checklist, Note

CLAUDE = ExternalAgentActor(client_id="claude-code", name="Claude Code")
REVIEWER = ExternalAgentActor(client_id="reviewer")


class RecordingBus:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def publish(self, event: Any) -> None:
        self.events.append(event)


class Identity:
    """Who the MCP client is; tests switch it to act as another client."""

    def __init__(self) -> None:
        self.tenant: TenantId = "tenant"
        self.actor = CLAUDE

    async def resolve(self, ctx: Context) -> tuple[TenantId, ExternalAgentActor]:
        return self.tenant, self.actor


@pytest.fixture
def identity() -> Identity:
    return Identity()


@pytest.fixture
def bus() -> RecordingBus:
    return RecordingBus()


@pytest.fixture
def workspaces() -> Workspaces:
    return Workspaces(InMemoryStorage(), types=[Note, Checklist])


@pytest.fixture
async def ws(workspaces: Workspaces) -> Workspace:
    return await workspaces.open("tenant", "w1", actor=UserActor(id="alice", name="Alice"))


@pytest.fixture
async def mcp(
    workspaces: Workspaces, identity: Identity, bus: RecordingBus, gate: Gate
) -> AsyncIterator[ArtifactrMcp]:
    from artifactr.agent import Runner

    script = Script(say("On it."), say("Also on it."))
    runner = Runner(make_agent(script), app=gate)
    server = ArtifactrMcp(workspaces, runner, resolve=identity.resolve, bus=cast(Any, bus))
    yield server
    await server.aclose()


@pytest.fixture
def gate() -> Gate:
    return Gate()


async def _call(client: Client, tool: str, **args: Any) -> tuple[bool, str]:
    result = await client.call_tool(tool, {"workspace_id": "w1", **args})
    return result.is_error, result.content[0].text  # type: ignore[union-attr]


async def test_artifact_tools(mcp: ArtifactrMcp) -> None:
    async with Client(mcp.server) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert {"read_artifact", "edit_text", "edit_artifact", "post_message"} <= tools
        assert await _call(client, "list_artifacts") == (False, "There are no artifacts yet.")
        error, created = await _call(
            client, "create_artifact", kind="note", data={"text": "Ship Friday"}
        )
        assert not error
        artifact_id = created.split()[1]
        assert (await _call(client, "list_artifacts", kind="note"))[
            1
        ] == f"- {artifact_id} (note, v1)"
        assert (await _call(client, "read_artifact", artifact_id=artifact_id))[1].endswith(
            "Ship Friday"
        )
        edited = await _call(
            client, "edit_text", artifact_id=artifact_id, old="Friday", new="Monday"
        )
        assert edited == (False, f"Done: {artifact_id} is now at version 2.")
        stale = await _call(
            client,
            "edit_text",
            artifact_id=artifact_id,
            old="Monday",
            new="Tuesday",
            base_version=1,
        )
        assert stale[0] is True
        assert "version 2" in stale[1]
        patched = await _call(
            client,
            "edit_artifact",
            artifact_id=artifact_id,
            base_version=2,
            ops=[{"op": "replace", "path": "/title", "value": "Launch"}],
        )
        assert patched == (False, f"Done: {artifact_id} is now at version 3.")
        assert (await _call(client, "archive_artifact", artifact_id=artifact_id))[1].endswith(
            "version 4."
        )
        assert (await _call(client, "create_artifact", kind="spreadsheet", data={}))[0] is True
        assert (await _call(client, "read_artifact", artifact_id="nope"))[0] is True
        assert (await _call(client, "archive_artifact", artifact_id="nope"))[0] is True


async def test_proposals_are_reviewed_by_someone_else(
    mcp: ArtifactrMcp, identity: Identity, ws: Workspace
) -> None:
    await ws.create(Note(text="Ship Friday"), artifact_id="n1")
    async with Client(mcp.server) as client:
        assert (await _call(client, "list_proposals"))[1] == "No proposals are awaiting review."
        proposed = await _call(
            client,
            "edit_text",
            artifact_id="n1",
            old="Friday",
            new="Monday",
            propose=True,
            rationale="safer",
        )
        assert proposed[1].startswith("Proposed as prp_")
        proposal_id = proposed[1].split()[2].rstrip(".")
        await _call(client, "create_artifact", kind="checklist", data={"title": "Beta"})
        listed = (await _call(client, "list_proposals"))[1].splitlines()
        assert listed[0] == f"- {proposal_id}: edit_artifact n1 by Claude Code (safer)"
        assert listed[1].endswith("by Claude Code")
        own = await _call(client, "respond_to_proposal", proposal_id=proposal_id, decision="accept")
        assert own[0] is True, "a proposal is resolved by someone other than its author"
        identity.actor = REVIEWER
        accepted = await _call(
            client, "respond_to_proposal", proposal_id=proposal_id, decision="accept"
        )
        assert accepted == (False, f"Accepted {proposal_id}: the artifact is now at version 2.")
        [checklist] = await ws.proposals()
        rejected = await _call(
            client, "respond_to_proposal", proposal_id=checklist.id, decision="reject"
        )
        assert rejected == (False, f"Rejected {checklist.id}.")


async def test_messages_reach_the_threads_agent(mcp: ArtifactrMcp, ws: Workspace) -> None:
    thread = await ws.create_thread("Launch")
    async with Client(mcp.server) as client:
        async with ws.claim_thread(thread.id, holder="another run"):
            steered = await _call(client, "post_message", thread_id=thread.id, content="Also this")
        assert steered[1] == "Posted; the agent already working in this thread will see it."
        started = await _call(client, "post_message", thread_id=thread.id, content="Plan it")
        assert started[1].startswith("Posted; the agent started run run_")
        assert (await _call(client, "post_message", thread_id="nope", content="hi"))[0] is True


async def test_artifacts_are_resources_of_their_tenant(
    mcp: ArtifactrMcp, identity: Identity, ws: Workspace
) -> None:
    await ws.create(Note(text="hello"), artifact_id="n1")
    async with Client(mcp.server) as client:
        result = await client.read_resource(artifact_uri("tenant", "w1", "n1"))
        body = json.loads(result.contents[0].text)  # type: ignore[union-attr]
        assert (body["id"], body["version"], body["data"]["text"]) == ("n1", 1, "hello")
        with pytest.raises(MCPError):
            await client.read_resource(artifact_uri("tenant", "w1", "nope"))
        identity.tenant = "intruder"
        with pytest.raises(MCPError):
            await client.read_resource(artifact_uri("tenant", "w1", "n1"))


async def test_changes_notify_resource_subscribers(
    mcp: ArtifactrMcp, bus: RecordingBus, ws: Workspace
) -> None:
    async with Client(mcp.server) as client:
        await _call(client, "list_artifacts")  # the server now follows w1
        await asyncio.sleep(0)
        await ws.create_thread("not an artifact")
        await ws.create(Note(), artifact_id="n1")
        for _ in range(50):
            if bus.events:
                break
            await asyncio.sleep(0.01)
    assert bus.events == [ResourceUpdated(uri=artifact_uri("tenant", "w1", "n1"))]


async def test_the_http_app_runs_in_a_lifespan(mcp: ArtifactrMcp) -> None:
    app = mcp.http_app(streamable_http_path="/")
    assert app is not None
    async with Client(mcp.server) as client:
        await _call(client, "list_artifacts")
    async with mcp.lifespan():
        pass


def test_resource_uris_carry_the_tenant() -> None:
    assert artifact_uri("t1", "w1", "n1") == "artifactr://t1/w1/artifacts/n1"


def test_the_agent_script_helpers_are_shared() -> None:
    assert call("x").parts[0].tool_name == "x"  # type: ignore[union-attr]
