"""artifactr's catalog bound to its workspaces and runner (lattice RFC-0014, artifactr ADR-0103).

Every command a client may call, carried out as artifactr's own surfaces carry it: writes
through the runner, once each, as the call's actor, in the call's workspace.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic import ValidationError
from pydantic_ai import FunctionToolset, RunContext

from artifactr.agent import Runner, Session
from artifactr.capabilities import FILES, ArtifactrCatalogProvider, CommandRejected
from artifactr.commands import CATALOG
from artifactr.core import Forbidden, NotFound, UserActor
from artifactr.workspace import Access, InMemoryStorage, Workspace, Workspaces
from lattice_core.capabilities import CallContext, Capability, PersonCaller, Scope, ToolResult
from lattice_core.commands import NotExposed
from lattice_core.taint import Clean
from tests.agent.conftest import Gate, Script, call, make_agent, say, settled
from tests.artifact_types import Checklist, Note

HERE = Scope(tenant_id="acme", workspace_id="docs")
ALEX = UserActor(id="alex")


def context(scope: Scope = HERE) -> CallContext:
    return CallContext(
        scope=scope,
        caller=PersonCaller(id="alex"),
        taint=Clean(),
        correlation_id="c1",
        surface="mcp",
    )


@pytest.fixture
def gate() -> Gate:
    return Gate()


@pytest.fixture
def app_tools() -> FunctionToolset[Session[Gate]]:
    tools = FunctionToolset[Session[Gate]]()

    @tools.tool
    async def hold(ctx: RunContext[Session[Gate]]) -> str:
        """Wait until the test releases the gate."""
        await ctx.deps.app.wait()
        return "released"

    return tools


@pytest.fixture
def workspaces() -> Workspaces:
    return Workspaces(InMemoryStorage(), types=[Note, Checklist])


@pytest.fixture
async def runner(
    gate: Gate, app_tools: FunctionToolset[Session[Gate]]
) -> AsyncIterator[Runner[Gate]]:
    made = Runner(
        make_agent(Script(call("hold"), say("Done."), say("Again.")), tools=[app_tools]), app=gate
    )
    yield made
    gate.release.set()
    await made.drain()
    await made.aclose()


@pytest.fixture
def provider(workspaces: Workspaces, runner: Runner[Gate]) -> ArtifactrCatalogProvider:
    return ArtifactrCatalogProvider(workspaces, runner, types=[Note, Checklist])


async def run(
    provider: ArtifactrCatalogProvider, name: str, scope: Scope = HERE, **arguments: Any
) -> str:
    [capability] = [c for c in provider.capabilities(scope) if c.name == name]
    result = await provider.call(capability, arguments, context(scope))
    assert isinstance(result, ToolResult)
    assert isinstance(result.output, str)
    return result.output


def kind_of(capability: Capability) -> Any:
    """The schema of a capability's ``kind`` argument."""
    return json.loads(json.dumps(capability.input_schema))["properties"]["kind"]


async def opened(workspaces: Workspaces) -> Workspace:
    return await workspaces.open("acme", "docs", actor=ALEX)


def test_it_offers_every_exposed_command_but_native_files(
    provider: ArtifactrCatalogProvider,
) -> None:
    exposed = {c.name for c in CATALOG.commands() if not isinstance(c.exposure, NotExposed)}
    offered = provider.capabilities(HERE)
    assert {c.name for c in offered} == exposed - FILES
    assert {"artifactr.answer_deferred", "artifactr.set_focus"}.isdisjoint(exposed)
    assert list(provider.commands()) == list(CATALOG.commands()), "it is the catalog too"
    [create] = [c for c in offered if c.name == "artifactr.create_artifact"]
    assert kind_of(create)["enum"] == ["note", "checklist"]
    assert create.description.startswith("Create an artifact of one of these kinds")
    [catalogs] = [c for c in CATALOG.commands() if c.name == "artifactr.create_artifact"]
    assert "enum" not in kind_of(catalogs.capability), "the catalog's own is unchanged"


async def test_workspaces_are_listed_on_the_tenant_whatever_the_call_names(
    provider: ArtifactrCatalogProvider, workspaces: Workspaces
) -> None:
    tenant = Scope(tenant_id="acme")
    assert await run(provider, "artifactr.list_workspaces", tenant) == "No workspaces."
    for name in ("docs", "plans"):
        await (await workspaces.open("acme", name, actor=ALEX)).create(Note(text=name))
    assert await run(provider, "artifactr.list_workspaces", tenant) == "docs\nplans"
    assert await run(provider, "artifactr.list_workspaces", HERE, after="docs") == "plans"


async def test_artifacts_are_made_read_edited_proposed_and_archived(
    provider: ArtifactrCatalogProvider, workspaces: Workspaces, runner: Runner[Gate]
) -> None:
    sam = ArtifactrCatalogProvider(
        workspaces, runner, types=[Note], actor=lambda _context: UserActor(id="sam")
    )
    made = await run(provider, "artifactr.create_artifact", kind="note", data={"text": "draft"})
    [note] = await (await opened(workspaces)).artifacts()
    assert made == f"Done: {note.id} is now at version 1."
    assert note.id in await run(provider, "artifactr.list_artifacts")
    assert "draft" in await run(provider, "artifactr.read_artifact", artifact_id=note.id)
    await run(provider, "artifactr.edit_text", artifact_id=note.id, old="draft", new="first")
    patch = [{"op": "replace", "path": "/text", "value": "second"}]
    await run(
        provider, "artifactr.edit_artifact", artifact_id=note.id, base_version=2, operations=patch
    )
    revisions = await run(provider, "artifactr.list_revisions", artifact_id=note.id)
    assert [json.loads(line)["version"] for line in revisions.splitlines()] == [1, 2, 3]
    proposed = await run(
        provider,
        "artifactr.propose_text",
        artifact_id=note.id,
        old="second",
        new="third",
        rationale="better",
    )
    assert "propos" in proposed.lower()
    [pending] = (await run(provider, "artifactr.list_proposals")).splitlines()
    proposal = json.loads(pending)
    assert proposal["rationale"] == "better"
    await run(sam, "artifactr.respond_to_proposal", proposal_id=proposal["id"], accept=False)
    assert await run(provider, "artifactr.list_proposals") == "No proposals are waiting."
    await run(provider, "artifactr.archive_artifact", artifact_id=note.id)
    archived = await (await opened(workspaces)).get(Note, note.id)
    assert (archived.archived, archived.data.text) == (True, "second")


async def test_a_message_starts_a_thread_and_its_agents_turn(
    provider: ArtifactrCatalogProvider, runner: Runner[Gate], gate: Gate, workspaces: Workspaces
) -> None:
    assert await run(provider, "artifactr.list_threads") == "There are no threads yet."
    started = await run(provider, "artifactr.post_message", text="Plan the launch.")
    assert started.startswith("Posted in thread ")
    assert "; the agent started run " in started
    thread_id = started.removeprefix("Posted in thread ").split(";")[0]
    await gate.entered.wait()
    joined = await run(
        provider, "artifactr.post_message", text="And the party.", thread_id=thread_id
    )
    assert joined == f"Posted in thread {thread_id}; the agent already working in it will see it."
    run_id = started.rsplit(" ", 1)[1].rstrip(".")
    read = json.loads(await run(provider, "artifactr.read_run", run_id=run_id))
    assert read["status"] == "running"
    gate.release.set()
    await settled(thread_id, runner)
    [listed] = (await run(provider, "artifactr.list_threads")).splitlines()
    assert json.loads(listed)["id"] == thread_id
    read_thread = json.loads(await run(provider, "artifactr.read_thread", thread_id=thread_id))
    assert read_thread["thread"]["id"] == thread_id
    assert "message_posted" in [e["event"]["type"] for e in read_thread["events"]]
    since = read_thread["events"][-1]["seq"]
    later = await run(provider, "artifactr.read_thread", thread_id=thread_id, after_seq=since)
    assert json.loads(later)["events"] == []
    events = await run(provider, "artifactr.read_events", limit=2)
    assert len(events.splitlines()) == 2
    assert await run(provider, "artifactr.read_events", after_seq=10_000) == "No events."


async def test_threads_are_started_their_mode_set_and_feedback_given(
    provider: ArtifactrCatalogProvider, workspaces: Workspaces
) -> None:
    started = await run(provider, "artifactr.create_thread", title="Launch")
    thread_id = started.removeprefix("Started thread ").rstrip(".")
    assert (await (await opened(workspaces)).thread(thread_id)).title == "Launch"
    untitled = await run(provider, "artifactr.create_thread")
    assert untitled.startswith("Started thread ")
    moded = await run(provider, "artifactr.set_thread_mode", thread_id=thread_id, mode="suggest")
    assert moded == f"Thread {thread_id} is in suggest mode."
    assert (await (await opened(workspaces)).thread(thread_id)).mode == "suggest"
    on_thread = {"kind": "thread", "thread_id": thread_id}
    given = await run(
        provider,
        "artifactr.give_feedback",
        feedback_type="helpfulness",
        target=on_thread,
        value={"rating": 5},
    )
    assert given == "Recorded helpfulness feedback on the thread."


async def test_a_running_run_is_stopped_and_one_that_isnt_refused(
    provider: ArtifactrCatalogProvider, gate: Gate
) -> None:
    started = await run(provider, "artifactr.post_message", text="Go.")
    run_id = started.rsplit(" ", 1)[1].rstrip(".")
    await gate.entered.wait()
    assert await run(provider, "artifactr.stop_run", run_id=run_id) == f"Stopped run {run_id}."
    with pytest.raises(CommandRejected) as refused:
        await run(provider, "artifactr.stop_run", run_id=run_id)
    assert refused.value.payload()["type"] == "not_found"
    assert refused.value.message == str(refused.value.payload()["message"])


async def test_what_the_workspace_refuses_is_raised(provider: ArtifactrCatalogProvider) -> None:
    with pytest.raises(NotFound):
        await run(provider, "artifactr.read_artifact", artifact_id="nope")
    with pytest.raises(CommandRejected) as refused:
        await run(provider, "artifactr.create_artifact", kind="note", data={"words": 1})
    assert refused.value.payload()["type"] == "validation_failed"
    with pytest.raises(ValidationError):
        await run(provider, "artifactr.set_thread_mode", thread_id="t", mode="shout")


async def test_a_call_is_refused_unless_its_command_is_offered_and_its_scope_fits(
    provider: ArtifactrCatalogProvider,
) -> None:
    [listing] = [c for c in provider.capabilities(HERE) if c.name == "artifactr.list_threads"]
    with pytest.raises(ValueError, match="is called in a workspace, and names none"):
        await provider.call(listing, {}, context(Scope(tenant_id="acme")))
    commands = {c.name: c for c in CATALOG.commands()}
    for name in ("artifactr.answer_deferred", "artifactr.read_file"):
        with pytest.raises(ValueError, match=f"{name} isn't a command this provider offers"):
            await provider.call(commands[name].capability, {}, context())
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        await provider.call(listing, {"limit": 2}, context())


async def test_each_call_opens_its_workspace_as_its_actor(gate: Gate) -> None:
    seen: list[tuple[str, str | None, str]] = []

    async def authorize(tenant: str, workspace: str | None, actor: Any, access: Access) -> bool:
        seen.append((tenant, workspace, access.action))
        return access.action != "artifactr:open" or workspace != "secret"

    guarded = Workspaces(InMemoryStorage(), types=[Note], authorize=authorize)
    runner = Runner(make_agent(Script()), app=gate)
    provider = ArtifactrCatalogProvider(guarded, runner, types=[Note])
    with pytest.raises(Forbidden):
        await run(
            provider, "artifactr.list_threads", Scope(tenant_id="acme", workspace_id="secret")
        )
    assert ("acme", "secret", "artifactr:open") in seen
    await run(provider, "artifactr.list_workspaces", Scope(tenant_id="acme"))
    assert ("acme", None, "artifactr:read_workspaces") in seen
    await runner.aclose()
    await asyncio.sleep(0)
