"""artifactr's provider: its artifact tools as capabilities, each opening the call's workspace as
the actor the call's context names (lattice RFC-0011, artifactr ADR-0099)."""

import pytest
from pydantic import JsonValue, ValidationError

from artifactr.capabilities import NAMES, VERSION, ArtifactrProvider, actor_for
from artifactr.core import (
    Actor,
    ExternalAgentActor,
    Forbidden,
    TenantId,
    UserActor,
    WorkspaceId,
)
from artifactr.workspace import Access, InMemoryStorage, Workspaces
from lattice_core.capabilities import (
    CallContext,
    Caller,
    PersonCaller,
    RunCaller,
    Scope,
    SessionCaller,
    Via,
)
from lattice_core.taint import Clean
from tests.artifact_types import Checklist, Note

HERE = Scope(tenant_id="acme", workspace_id="docs")
ALEX = UserActor(id="alex")
CLAUDE = Via(connection_id="con_1", client_name="Claude", surface="mcp")


def context(caller: Caller | None = None, via: Via | None = None) -> CallContext:
    return CallContext(
        scope=HERE,
        caller=caller or PersonCaller(id="alex"),
        taint=Clean(),
        correlation_id="c1",
        surface="portalr",
        via=via,
    )


async def call(
    provider: ArtifactrProvider,
    name: str,
    arguments: dict[str, JsonValue],
    within: CallContext | None = None,
) -> JsonValue:
    [capability] = [c for c in provider.capabilities(HERE) if c.name == name]
    return (await provider.call(capability, arguments, within or context())).output


@pytest.fixture
def workspaces() -> Workspaces:
    return Workspaces(InMemoryStorage(), types=[Note, Checklist])


def test_the_tools_are_offered_as_command_capabilities_the_same_in_every_workspace(
    workspaces: Workspaces,
) -> None:
    provider = ArtifactrProvider(workspaces, types=[Note, Checklist])
    offered = provider.capabilities(HERE)
    assert provider.kind == "command"
    assert tuple(c.name for c in offered) == NAMES
    reads = frozenset({"reads_private"})
    assert {c.name: (c.tier, c.gate.action, c.effects, c.reversibility) for c in offered} == {
        "artifactr.list_artifacts": ("read", "artifactr:read_artifacts", reads, "none"),
        "artifactr.read_artifact": ("read", "artifactr:read_artifacts", reads, "none"),
        "artifactr.create_artifact": (
            "write",
            "artifactr:create_artifact",
            frozenset(),
            "compensable",
        ),
        "artifactr.edit_text": ("write", "artifactr:edit_artifact", frozenset(), "compensable"),
        "artifactr.propose_text": ("write", "artifactr:propose_change", frozenset(), "undoable"),
        "artifactr.archive_artifact": (
            "write",
            "artifactr:archive_artifact",
            frozenset(),
            "irreversible",
        ),
    }
    for capability in offered:
        assert capability.version == VERSION
        assert capability.provider == "command"
        assert capability.gate.integration is None
        assert capability.output_schema == {"type": "string"}
        assert capability.input_schema["additionalProperties"] is False
        assert "title" not in capability.input_schema
    assert provider.capabilities(Scope(tenant_id="other", workspace_id="w")) == offered


def test_create_artifact_names_the_kinds_a_caller_may_create_and_describes_each(
    workspaces: Workspaces,
) -> None:
    [create] = [
        c
        for c in ArtifactrProvider(workspaces, types=[Note]).capabilities(HERE)
        if c.name == "artifactr.create_artifact"
    ]
    properties = create.input_schema["properties"]
    assert isinstance(properties, dict)
    kind = properties["kind"]
    assert isinstance(kind, dict)
    assert kind["enum"] == ["note"]
    assert "\n- note: {" in create.description


async def test_each_capability_does_what_its_tool_does_as_the_callers_actor(
    workspaces: Workspaces,
) -> None:
    provider = ArtifactrProvider(workspaces, types=[Note, Checklist])
    data: dict[str, JsonValue] = {"text": "Ship on Friday"}
    created = await call(provider, "artifactr.create_artifact", {"kind": "note", "data": data})
    ws = await workspaces.open("acme", "docs", actor=ALEX)
    [artifact] = await ws.artifacts()
    assert created == f"Done: {artifact.id} is now at version 1."
    assert artifact.updated_by == ALEX
    listed = await call(provider, "artifactr.list_artifacts", {})
    assert listed == f"- {artifact.id} (note, v1)"
    none = await call(provider, "artifactr.list_artifacts", {"kind": "checklist"})
    assert none == "There are no artifacts yet."
    read = await call(provider, "artifactr.read_artifact", {"artifact_id": artifact.id})
    assert read == f"{artifact.id} (note, v1)\n\nShip on Friday"
    edit: dict[str, JsonValue] = {"artifact_id": artifact.id, "old": "Friday", "new": "Monday"}
    edited = await call(provider, "artifactr.edit_text", edit)
    assert edited == f"Done: {artifact.id} is now at version 2."
    proposal: dict[str, JsonValue] = {
        "artifact_id": artifact.id,
        "old": "Monday",
        "new": "Tuesday",
        "summary": "A day later",
        "rationale": "The venue is booked on Monday.",
    }
    proposed = await call(provider, "artifactr.propose_text", proposal)
    [pending] = await ws.proposals()
    assert proposed == (
        f"Proposed as {pending.id}. A person will review it; you will be told whether it was "
        "accepted."
    )
    assert (pending.rationale, pending.proposed_by) == ("The venue is booked on Monday.", ALEX)
    assert (await ws.get(Note, artifact.id)).data.text == "Ship on Monday"
    archived = await call(provider, "artifactr.archive_artifact", {"artifact_id": artifact.id})
    assert archived == f"Done: {artifact.id} is now at version 3."
    assert (await ws.artifact(artifact.id)).archived


@pytest.mark.parametrize(
    ("caller", "via", "actor"),
    [
        (PersonCaller(id="alex"), None, ALEX),
        (
            PersonCaller(id="alex"),
            CLAUDE,
            ExternalAgentActor(client_id="con_1", name="Claude", on_behalf_of=ALEX),
        ),
        (
            RunCaller(id="run_1", agent="triage", on_behalf_of="alex"),
            None,
            ExternalAgentActor(client_id="agent:triage", name="triage", on_behalf_of=ALEX),
        ),
        (
            RunCaller(id="run_1", agent="triage"),
            None,
            ExternalAgentActor(client_id="agent:triage", name="triage"),
        ),
        (
            SessionCaller(id="ses_1", on_behalf_of="alex"),
            None,
            ExternalAgentActor(client_id="session:ses_1", name="code session", on_behalf_of=ALEX),
        ),
        (
            SessionCaller(id="ses_1"),
            CLAUDE,
            ExternalAgentActor(client_id="con_1", name="Claude"),
        ),
    ],
)
def test_a_calls_actor_is_the_client_it_came_through_or_else_its_caller(
    caller: Caller, via: Via | None, actor: Actor
) -> None:
    assert actor_for(context(caller, via)) == actor


async def test_the_workspace_hears_each_call_as_its_actor_and_may_refuse_it() -> None:
    asked: list[tuple[str, str]] = []

    async def authorize(
        tenant_id: TenantId, workspace_id: WorkspaceId | None, actor: Actor, access: Access
    ) -> bool:
        asked.append((actor.participant, access.action))
        return access.action != "artifactr:create_artifact"

    workspaces = Workspaces(InMemoryStorage(), types=[Note], authorize=authorize)
    provider = ArtifactrProvider(workspaces, types=[Note])
    within = context(PersonCaller(id="alex"), CLAUDE)
    with pytest.raises(Forbidden, match="artifactr:create_artifact is refused"):
        await call(provider, "artifactr.create_artifact", {"kind": "note", "data": {}}, within)
    client = "external_agent:con_1"
    assert asked == [(client, "artifactr:open"), (client, "artifactr:create_artifact")]


async def test_an_application_may_build_each_calls_actor_itself(workspaces: Workspaces) -> None:
    sam = UserActor(id="sam", name="Sam")
    provider = ArtifactrProvider(workspaces, types=[Note], actor=lambda _context: sam)
    run = context(RunCaller(id="run_1", agent="triage"))
    await call(provider, "artifactr.create_artifact", {"kind": "note", "data": {}}, run)
    [artifact] = await (await workspaces.open("acme", "docs", actor=sam)).artifacts()
    assert artifact.updated_by == sam


async def test_arguments_that_arent_the_capabilitys_are_refused_before_the_workspace_opens() -> (
    None
):
    opened: list[str] = []

    async def on_open(tenant_id: TenantId, workspace_id: WorkspaceId) -> None:
        opened.append(workspace_id)

    provider = ArtifactrProvider(Workspaces(InMemoryStorage(), on_open=on_open), types=[Note])
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        await call(provider, "artifactr.read_artifact", {"artifact_id": "a", "version": 2})
    with pytest.raises(ValidationError, match="artifact_id"):
        await call(provider, "artifactr.archive_artifact", {})
    assert opened == []


async def test_another_providers_capability_is_refused(workspaces: Workspaces) -> None:
    provider = ArtifactrProvider(workspaces, types=[Note])
    foreign = provider.capabilities(HERE)[0].model_copy(update={"name": "notes.list"})
    with pytest.raises(ValueError, match="notes.list isn't one of artifactr's capabilities"):
        await provider.call(foreign, {}, context())
