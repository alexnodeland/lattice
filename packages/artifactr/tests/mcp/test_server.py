"""External agents over MCP: tools, resources and change notifications."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any, assert_type

import pytest
from mcp import Client
from mcp.server.mcpserver import Context
from mcp.server.subscriptions import InMemorySubscriptionBus, ResourceUpdated, ServerEvent
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS, TextContent, TextResourceContents
from starlette.requests import Request

from artifactr.agent import Runner
from artifactr.core import Actor, ExternalAgentActor, TenantId, UserActor, WorkspaceId
from artifactr.mcp import ArtifactrMcp, McpContext, artifact_uri
from artifactr.workspace import InMemoryStorage, Workspace, Workspaces
from tests.agent.conftest import Gate, Script, make_agent, say
from tests.artifact_types import Checklist, Note

CLAUDE = ExternalAgentActor(client_id="claude-code", name="Claude Code")
REVIEWER = ExternalAgentActor(client_id="reviewer")
ALICE = UserActor(id="alice", name="Alice")
FORBIDDEN = "this workspace is not yours to use"


class RecordingBus(InMemorySubscriptionBus):
    """The in-process bus, remembering what was published."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[ServerEvent] = []

    async def publish(self, event: ServerEvent) -> None:
        self.events.append(event)
        await super().publish(event)


class Identity:
    """Who the MCP client is; tests switch it to act as another client."""

    def __init__(self) -> None:
        self.tenant: TenantId = "tenant"
        self.actor = CLAUDE
        self.resolved = 0

    async def resolve(self, ctx: Context) -> tuple[TenantId, ExternalAgentActor]:
        self.resolved += 1
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
    return await workspaces.open("tenant", "w1", actor=ALICE)


@pytest.fixture
async def mcp(
    workspaces: Workspaces, identity: Identity, bus: RecordingBus, gate: Gate
) -> AsyncIterator[ArtifactrMcp]:
    script = Script(say("On it."), say("Also on it."))
    runner = Runner(make_agent(script), app=gate)
    server = ArtifactrMcp(workspaces, runner, resolve=identity.resolve, bus=bus)
    yield server
    await server.aclose()


@pytest.fixture
def gate() -> Gate:
    return Gate()


async def _call(client: Client, tool: str, **args: Any) -> tuple[bool, str]:
    result = await client.call_tool(tool, {"workspace_id": "w1", **args})
    content = result.content[0]
    assert isinstance(content, TextContent)
    return result.is_error, content.text


async def _wait_for_run(ws: Workspace, run_id: str) -> None:
    """Wait until a run the server started has ended."""
    for _ in range(200):
        if any(run.id == run_id and run.status != "running" for run in await ws.runs()):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"run {run_id} did not end")


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
        assert (await _call(client, "list_artifacts"))[1] == "There are no artifacts yet."
        archived = await _call(client, "list_artifacts", include_archived=True)
        assert archived == (False, f"- {artifact_id} (note, v4, archived)")
        assert (await _call(client, "create_artifact", kind="spreadsheet", data={}))[0] is True
        assert (await _call(client, "read_artifact", artifact_id="nope"))[0] is True
        assert (await _call(client, "archive_artifact", artifact_id="nope"))[0] is True


async def test_agents_read_the_log_from_its_end_and_backwards(
    mcp: ArtifactrMcp, ws: Workspace
) -> None:
    one = await ws.create_thread("one")
    for number in range(59):
        await ws.create_thread(f"thread {number}")

    async def seqs(**args: Any) -> list[int]:
        _, lines = await _call(client, "read_events", **args)
        return [json.loads(line)["seq"] for line in lines.splitlines()]

    async with Client(mcp.server) as client:
        assert await seqs() == list(range(1, 51)), "the first 50 by default"
        assert await seqs(limit=60) == list(range(1, 61))
        assert await seqs(last=3) == [58, 59, 60]
        assert await seqs(last=2, threads=[one.id]) == [1]
        assert await seqs(last=2, before_seq=41) == [39, 40]
        assert await seqs(after_seq=5, before_seq=8) == [6, 7]
        assert await _call(client, "read_events", after_seq=60) == (False, "No events.")
        both = await _call(client, "read_events", limit=1, last=1)
        assert both == (True, "Error executing tool read_events: give limit or last, not both")


async def test_a_retried_command_is_carried_out_once(mcp: ArtifactrMcp, ws: Workspace) -> None:
    async with Client(mcp.server) as client:
        create = {"kind": "note", "data": {"text": "Ship Friday"}, "command_id": "c1"}
        created = await _call(client, "create_artifact", **create)
        assert await _call(client, "create_artifact", **create) == created, "the first result"
    assert len(await ws.artifacts()) == 1


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
        assert listed[0] == f"- {proposal_id}: edit_artifact n1 by Claude Code, pending (safer)"
        assert listed[1].endswith("by Claude Code, pending")
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
        assert (await _call(client, "list_proposals"))[1] == "No proposals are awaiting review."
        accepted_only = (await _call(client, "list_proposals", status="accepted"))[1]
        assert (
            accepted_only == f"- {proposal_id}: edit_artifact n1 by Claude Code, accepted (safer)"
        )
        assert len((await _call(client, "list_proposals", status=None))[1].splitlines()) == 2
        assert (await _call(client, "list_proposals", status="rejected"))[1].endswith("rejected")
        elsewhere = await _call(client, "list_proposals", workspace_id="w2", status=None)
        assert elsewhere == (False, "No proposals have been made.")


async def test_messages_reach_the_threads_agent(mcp: ArtifactrMcp, ws: Workspace) -> None:
    thread = await ws.create_thread("Launch")
    async with Client(mcp.server) as client:
        async with ws.claim_thread(thread.id, holder="another run"):
            steered = await _call(client, "post_message", thread_id=thread.id, content="Also this")
        assert steered[1] == "Posted; the agent already working in this thread will see it."
        started = await _call(client, "post_message", thread_id=thread.id, content="Plan it")
        assert started[1].startswith("Posted; the agent started run run_")
        run_id = started[1].removeprefix("Posted; the agent started run ").rstrip(".")
        await _wait_for_run(ws, run_id)
        error, run = await _call(client, "get_run", run_id=run_id)
        assert not error
        assert json.loads(run) == (await ws.run(run_id)).model_dump(mode="json")
        assert json.loads(run)["status"] == "completed"
        assert (await _call(client, "post_message", thread_id="nope", content="hi"))[0] is True
        assert (await _call(client, "get_run", run_id="run_nope"))[0] is True


async def test_threads_and_revisions_are_read_as_rest_reads_them(
    mcp: ArtifactrMcp, ws: Workspace
) -> None:
    async with Client(mcp.server) as client:
        assert await _call(client, "list_threads") == (False, "There are no threads yet.")
        first = await ws.create_thread("Launch")
        second = await ws.create_thread("Hiring")
        lines = (await _call(client, "list_threads"))[1].splitlines()
        assert [json.loads(line)["id"] for line in lines] == [first.id, second.id]
        error, thread = await _call(client, "get_thread", thread_id=first.id)
        assert (error, json.loads(thread)) == (False, first.model_dump(mode="json"))
        assert (await _call(client, "get_thread", thread_id="nope"))[0] is True
        await ws.create(Note(text="Ship Friday"), artifact_id="n1")
        await ws.commit((await ws.artifact("n1")).edit_text("Friday", "Monday"))
        error, revisions = await _call(client, "list_revisions", artifact_id="n1")
        assert not error
        expected = [r.model_dump(mode="json") for r in await ws.revisions("n1")]
        assert [json.loads(line) for line in revisions.splitlines()] == expected
        assert [r["version"] for r in expected] == [1, 2]
        missing = await _call(client, "list_revisions", artifact_id="nope")
        assert missing == (
            True,
            "Error executing tool list_revisions: artifact nope does not exist",
        )


async def test_artifacts_are_resources_of_their_tenant(
    mcp: ArtifactrMcp, identity: Identity, ws: Workspace
) -> None:
    await ws.create(Note(text="hello"), artifact_id="n1")
    async with Client(mcp.server) as client:
        resolved = identity.resolved
        result = await client.read_resource(artifact_uri("tenant", "w1", "n1"))
        assert identity.resolved == resolved + 1, "a read resolves its client once"
        contents = result.contents[0]
        assert isinstance(contents, TextResourceContents)
        body = json.loads(contents.text)
        assert (body["id"], body["kind"], body["version"]) == ("n1", "note", 1)
        assert body["data"]["text"] == "hello"
        missing = artifact_uri("tenant", "w1", "nope")
        with pytest.raises(MCPError, match="artifact nope does not exist") as read:
            await client.read_resource(missing)
        assert read.value.code == INVALID_PARAMS, "a refusal, not a failure of the server"
        assert read.value.data == {
            "uri": missing,
            "rejection": {
                "type": "not_found",
                "message": "artifact nope does not exist",
                "entity": "artifact",
                "id": "nope",
            },
        }
        async with client.listen(resource_subscriptions=[artifact_uri("tenant", "w1", "n1")]):
            pass
        identity.tenant = "intruder"
        with pytest.raises(MCPError, match="tenant tenant are not available") as other:
            await client.read_resource(artifact_uri("tenant", "w1", "n1"))
        assert other.value.code == INVALID_PARAMS
        assert other.value.data["rejection"]["type"] == "forbidden"
        with pytest.raises(MCPError, match="artifact resources of tenant tenant are not available"):
            async with client.listen(resource_subscriptions=[artifact_uri("tenant", "w1", "n1")]):
                pass
        others = ["file:///elsewhere"]  # not an artifact, so not checked
        async with client.listen(tools_list_changed=True, resource_subscriptions=others) as sub:
            assert sub.honored.resource_subscriptions == others


async def test_authorize_decides_which_workspaces_a_client_may_use(
    workspaces: Workspaces, ws: Workspace, bus: RecordingBus, gate: Gate
) -> None:
    asked: list[tuple[TenantId, WorkspaceId, str]] = []

    async def authorize(tenant_id: TenantId, workspace_id: WorkspaceId, actor: Actor) -> bool:
        asked.append((tenant_id, workspace_id, actor.kind))
        return workspace_id != "secret"

    secret = await workspaces.open("tenant", "secret", actor=ALICE)
    await secret.create(Note(text="classified"), artifact_id="n1")
    thread = await secret.create_thread("Plans")
    head = await secret.head_seq()
    runner = Runner(make_agent(Script(say("On it."))), app=gate)
    mcp = ArtifactrMcp(workspaces, runner, resolve=Identity().resolve, authorize=authorize, bus=bus)
    n1 = {"artifact_id": "n1"}
    replace = [{"op": "replace", "path": "/text", "value": "public"}]
    on_thread = {"kind": "thread", "thread_id": thread.id}
    tools: dict[str, dict[str, Any]] = {
        "list_artifacts": {},
        "read_artifact": n1,
        "list_revisions": n1,
        "create_artifact": {"kind": "note", "data": {"text": "leak"}},
        "edit_text": {**n1, "old": "classified", "new": "public"},
        "edit_artifact": {**n1, "base_version": 1, "ops": replace},
        "archive_artifact": n1,
        "list_proposals": {},
        "respond_to_proposal": {"proposal_id": "prp_1", "decision": "accept"},
        "give_feedback": {"feedback_type": "helpfulness", "target": on_thread, "value": {}},
        "post_message": {"thread_id": thread.id, "content": "hi"},
        "read_events": {},
        "list_threads": {},
        "get_thread": {"thread_id": thread.id},
        "get_run": {"run_id": "run_1"},
    }
    try:
        async with Client(mcp.server) as client:
            served = {tool.name for tool in (await client.list_tools()).tools}
            assert served == set(tools), "every tool names a workspace"
            for tool, args in tools.items():
                error, text = await _call(client, tool, **{**args, "workspace_id": "secret"})
                assert (error, text.endswith(FORBIDDEN)) == (True, True), tool
            uri = artifact_uri("tenant", "secret", "n1")
            with pytest.raises(MCPError, match=FORBIDDEN) as read:
                await client.read_resource(uri)
            forbidden = {"type": "forbidden", "message": FORBIDDEN}
            assert (read.value.code, read.value.data) == (
                INVALID_PARAMS,
                {"uri": uri, "rejection": forbidden},
            )
            with pytest.raises(MCPError, match=FORBIDDEN) as listen:
                async with client.listen(resource_subscriptions=[uri]):
                    pass
            assert listen.value.data == read.value.data, "a subscription is refused as a read is"
            assert (await _call(client, "list_artifacts"))[0] is False  # w1 is followed now
            await asyncio.sleep(0)
            await secret.create(Note(), artifact_id="n2")
            await ws.create(Note(), artifact_id="n3")
            for _ in range(50):
                if bus.events:
                    break
                await asyncio.sleep(0.01)
    finally:
        await mcp.aclose()
    assert asked.count(("tenant", "secret", "external_agent")) == len(tools) + 2
    assert asked[-1] == ("tenant", "w1", "external_agent")
    assert await secret.head_seq() == head + 1, "the client wrote nothing"
    assert bus.events == [ResourceUpdated(uri=artifact_uri("tenant", "w1", "n3"))], "nor followed"


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


async def test_a_resolver_reads_its_request_without_a_cast(
    workspaces: Workspaces, ws: Workspace, gate: Gate
) -> None:
    async def resolve(ctx: McpContext) -> tuple[TenantId, ExternalAgentActor]:
        request = assert_type(ctx.request_context.request, Request | None)
        name = "in process" if request is None else request.headers.get("x-client")
        return "tenant", ExternalAgentActor(client_id="typed", name=name)

    runner = Runner(make_agent(Script()), app=gate)
    server = ArtifactrMcp(workspaces, runner, resolve=resolve)
    try:
        async with Client(server.server) as client:
            await _call(client, "create_artifact", kind="note", data={"text": "hi"})
    finally:
        await server.aclose()
    [note] = await ws.artifacts()
    assert note.updated_by == ExternalAgentActor(client_id="typed", name="in process")


def test_resource_uris_carry_the_tenant() -> None:
    assert artifact_uri("t1", "w1", "n1") == "artifactr://t1/w1/artifacts/n1"


async def test_external_agents_give_feedback(mcp: ArtifactrMcp, ws: Workspace) -> None:
    thread = await ws.create_thread("Launch")
    async with Client(mcp.server) as client:
        given = await _call(
            client,
            "give_feedback",
            feedback_type="helpfulness",
            target={"kind": "thread", "thread_id": thread.id},
            value={"rating": 4},
        )
        assert given == (False, "Recorded helpfulness feedback on the thread.")
        invalid = await _call(
            client,
            "give_feedback",
            feedback_type="helpfulness",
            target={"kind": "thread", "thread_id": thread.id},
        )
        assert invalid[0] is True, "a rating is required"
    [envelope] = await ws.read(after_seq=1)
    assert envelope.actor == CLAUDE
    assert envelope.event.type == "feedback_given"


async def test_building_the_server_leaves_logging_as_it_was(
    workspaces: Workspaces, identity: Identity, gate: Gate, monkeypatch: pytest.MonkeyPatch
) -> None:
    # As in an application that has not configured logging: the SDK's server would otherwise
    # give the root logger a rich handler and set the whole process to INFO.
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", logging.WARNING)
    runner = Runner(make_agent(Script()), app=gate)
    await ArtifactrMcp(workspaces, runner, resolve=identity.resolve).aclose()
    assert (root.handlers, root.level) == ([], logging.WARNING)
