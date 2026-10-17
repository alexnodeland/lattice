"""The gate (ADR-0081): an integration switched off answers NotEnabled, after hidden, before access.

Notes are governed by the ``notes`` integration here, as an application's ``key_of`` would name
one; checklists by none. Bob is the actor; Alice fills the workspace while it is on. Each
behaviour runs over every storage.
"""

import itertools
from collections.abc import Mapping

import pytest
from pydantic import JsonValue

from artifactr.core import (
    Actor,
    AppEvent,
    ArchiveArtifact,
    Command,
    CreateArtifact,
    CreateThread,
    EditArtifact,
    Forbidden,
    NotEnabled,
    NotFound,
    ProposeChange,
    RespondToProposal,
    TenantId,
    UserActor,
    ValidationFailed,
    Visibility,
    WorkspaceId,
    create_artifact,
)
from artifactr.workspace import (
    Access,
    Changes,
    Gate,
    Storage,
    Workspace,
    Workspaces,
    integration_gate,
)
from tests.artifact_types import Checklist, Note
from tests.workspace.gating import NOTES, Switch, key_of

ALICE = UserActor(id="alice", name="Alice")
BOB = UserActor(id="bob", name="Bob")


class Bob:
    """What Bob may see and do: everything, until a test says otherwise. It records the order."""

    def __init__(self, switch: Switch) -> None:
        self.refused = False
        self.hidden: frozenset[str] = frozenset()
        self.calls = switch.calls
        self.gate = integration_gate(switch, key_of)

    async def authorize(
        self, tenant_id: TenantId, workspace_id: WorkspaceId | None, actor: Actor, access: Access
    ) -> bool:
        if actor != BOB:
            return True
        self.calls.append(f"authorize {access.action}")
        return not self.refused or access.action == "artifactr:open"

    async def hides(
        self, tenant_id: TenantId, workspace_id: WorkspaceId, actor: Actor
    ) -> Visibility:
        return Visibility(artifacts=self.hidden) if actor == BOB else Visibility()

    async def gated(
        self,
        workspace: Workspace,
        command: Command,
        changes: Changes,
    ) -> None:
        self.calls.append(f"gate {command.type}")
        await self.gate(workspace, command, changes)


@pytest.fixture
def switch() -> Switch:
    return Switch()


@pytest.fixture
def bob(switch: Switch) -> Bob:
    return Bob(switch)


def _workspaces(storage: Storage, bob: Bob, gate: Gate | None = None) -> Workspaces:
    return Workspaces(
        storage,
        types=[Note, Checklist],
        authorize=bob.authorize,
        hidden=bob.hides,
        gate=gate or bob.gated,
    )


async def _fill(workspaces: Workspaces, tenant_id: TenantId = "acme") -> Workspace:
    """Alice's note n1 with a pending proposal p1, and a checklist c1; Bob's handle on them."""
    alice = await workspaces.open(tenant_id, "w1", actor=ALICE)
    await alice.create(Note(text="Ship Friday"), artifact_id="n1")
    await alice.create(Checklist(title="Launch"), artifact_id="c1")
    edit = (await alice.get(Note, "n1")).edit_text("Friday", "Monday")
    await alice.commit(ProposeChange(proposal_id="p1", change=edit))
    return await workspaces.open(tenant_id, "w1", actor=BOB)


@pytest.fixture
async def ws(storage: Storage, bob: Bob) -> Workspace:
    return await _fill(_workspaces(storage, bob))


def _off(switch: Switch, tenant_id: TenantId = "acme") -> None:
    switch.off.add((tenant_id, "w1", NOTES))
    switch.calls.clear()


async def _edit(ws: Workspace) -> EditArtifact:
    return (await ws.get(Note, "n1")).edit_text("Ship", "Send")


def _accept(proposal_id: str = "p1") -> RespondToProposal:
    return RespondToProposal(proposal_id=proposal_id, decision="accept")


# ─── what the gate refuses while off ─────────────────────────────────────────


async def test_changes_to_a_governed_artifact_are_refused_while_its_integration_is_off(
    ws: Workspace, switch: Switch
) -> None:
    edit = await _edit(ws)
    created = create_artifact(Note(text="new"), artifact_id="n2")
    _off(switch)
    for command in (
        created,
        edit,
        ProposeChange(change=created),
        ProposeChange(change=edit),
        _accept(),
    ):
        with pytest.raises(NotEnabled) as refused:
            await ws.commit(command)
        assert refused.value.payload() == {
            "type": "not_enabled",
            "message": "notes is not available in this workspace",
            "integration": NOTES,
        }
    assert (await ws.proposal("p1")).status == "pending", "it waits until notes are on again"


async def test_accepting_a_proposed_note_is_refused_too(
    storage: Storage, bob: Bob, switch: Switch
) -> None:
    ws = await _fill(_workspaces(storage, bob))
    await ws.as_actor(ALICE).commit(
        ProposeChange(proposal_id="p2", change=create_artifact(Note(text="new"), artifact_id="n2"))
    )
    _off(switch)
    with pytest.raises(NotEnabled):
        await ws.commit(_accept("p2"))
    switch.off.clear()
    await ws.commit(_accept("p2"))
    assert (await ws.get(Note, "n2")).data.text == "new", "accepted once notes are on again"


async def test_tidying_up_passes_while_off(ws: Workspace, switch: Switch) -> None:
    _off(switch)
    await ws.commit(RespondToProposal(proposal_id="p1", decision="reject"))
    head = await ws.get(Note, "n1")
    await ws.commit(ProposeChange(change=ArchiveArtifact(artifact_id="n1", base_version=1)))
    await ws.commit(ArchiveArtifact(artifact_id="n1", base_version=head.version))
    assert (await ws.artifact("n1")).archived
    assert "is_enabled notes" not in switch.calls, "the integration is not asked to tidy up"


async def test_what_no_integration_governs_passes_without_asking(
    ws: Workspace, switch: Switch
) -> None:
    _off(switch)
    checklist = await ws.get(Checklist, "c1")
    await ws.commit(checklist.edit(lambda c: setattr(c, "title", "Liftoff")))
    await ws.create(Checklist(), artifact_id="c2")
    await ws.commit(CreateThread(thread_id="t1"))
    await ws.post_message("t1", "hello")
    assert "is_enabled notes" not in switch.calls


async def test_an_edit_of_a_missing_artifact_is_missing(ws: Workspace, switch: Switch) -> None:
    _off(switch)
    with pytest.raises(NotFound):
        await ws.commit(ArchiveArtifact(artifact_id="n9", base_version=1))
    with pytest.raises(NotFound):
        await ws.commit(RespondToProposal(proposal_id="p9", decision="accept"))


async def test_the_gate_hears_what_the_command_changes(storage: Storage, bob: Bob) -> None:
    heard: list[tuple[str, str | None]] = []

    async def gate(workspace: Workspace, command: Command, changes: Changes) -> None:
        heard.append((command.type, None if changes is None else changes.kind))

    ws = await _fill(_workspaces(storage, bob, gate))
    await ws.as_actor(ALICE).commit(
        ProposeChange(proposal_id="p2", change=ArchiveArtifact(artifact_id="c1", base_version=1))
    )
    heard.clear()
    await ws.commit(RespondToProposal(proposal_id="p2", decision="reject"))
    await ws.commit(_accept())
    await ws.commit(ArchiveArtifact(artifact_id="n1", base_version=2))
    await ws.create(Checklist(), artifact_id="c2")
    await ws.commit(CreateThread())
    assert heard == [
        ("respond_to_proposal", None),
        ("respond_to_proposal", "note"),
        ("archive_artifact", None),
        ("create_artifact", "checklist"),
        ("create_thread", None),
    ], "what changes no data is not read"


async def test_key_of_reads_the_data_as_json(storage: Storage, switch: Switch) -> None:
    read: list[Mapping[str, JsonValue]] = []

    def by_title(kind: str, data: Mapping[str, JsonValue]) -> str | None:
        read.append(data)
        return None

    ws = await Workspaces(storage, gate=integration_gate(switch, by_title)).open(
        "acme", "w1", actor=ALICE
    )
    await ws.commit(CreateArtifact(artifact_id="n1", kind="note", data={}))
    await ws.commit((await ws.get(Note, "n1")).edit(lambda note: setattr(note, "text", "Ship")))
    assert read == [{"text": "", "title": ""}] * 2, "a create's defaults, as an edit's"


async def test_a_create_that_is_not_its_type_is_refused_by_core(
    ws: Workspace, switch: Switch
) -> None:
    _off(switch)
    with pytest.raises(ValidationFailed):
        await ws.commit(CreateArtifact(kind="note", data={"text": 5}))
    with pytest.raises(NotFound):
        await ws.commit(CreateArtifact(kind="sketch", data={}))
    assert "is_enabled notes" not in switch.calls


# ─── the order: hidden, then the gate, then authorize ────────────────────────


async def test_off_answers_not_enabled_to_someone_with_no_grants(
    ws: Workspace, bob: Bob, switch: Switch
) -> None:
    bob.refused = True
    _off(switch)
    with pytest.raises(NotEnabled):
        await ws.commit(await _edit(ws.as_actor(ALICE)))
    with pytest.raises(NotEnabled):
        await ws.commit(_accept())


@pytest.mark.parametrize("off", [True, False])
async def test_a_hidden_target_is_missing_and_never_gated(
    ws: Workspace, bob: Bob, switch: Switch, off: bool
) -> None:
    edit = await _edit(ws.as_actor(ALICE))
    bob.hidden = frozenset({"n1"})
    bob.refused = True
    if off:
        _off(switch)
    switch.calls.clear()
    with pytest.raises(NotFound) as missing:
        await ws.commit(edit)
    assert missing.value.details() == {"entity": "artifact", "id": "n1"}
    with pytest.raises(NotFound) as missing:
        await ws.commit(_accept())
    assert missing.value.details() == {"entity": "proposal", "id": "p1"}
    assert switch.calls == [], "neither the gate, the integration nor authorize is asked"


async def test_on_authorize_still_refuses(ws: Workspace, bob: Bob) -> None:
    edit = await _edit(ws)
    bob.refused = True
    with pytest.raises(Forbidden):
        await ws.commit(edit)


async def test_the_gate_is_asked_before_authorize(ws: Workspace, switch: Switch) -> None:
    edit = await _edit(ws)
    switch.calls.clear()
    await ws.commit(edit)
    await ws.commit(_accept())
    assert switch.calls == [
        "gate edit_artifact",
        "is_enabled notes",
        "authorize artifactr:edit_artifact",
        "gate respond_to_proposal",
        "is_enabled notes",
        "authorize artifactr:respond_to_proposal",
        "authorize artifactr:respond_to_proposal",
    ]


# ─── what is never gated ─────────────────────────────────────────────────────


async def test_reads_and_facts_are_not_gated(ws: Workspace, switch: Switch) -> None:
    _off(switch)
    assert (await ws.get(Note, "n1")).data.text == "Ship Friday"
    assert (await ws.artifact("n1")).kind == "note"
    assert [r.version for r in await ws.revisions("n1")] == [1]
    assert [p.id for p in await ws.proposals()] == ["p1"]
    assert len(await ws.read()) == 3
    await ws.record(AppEvent(name="noted"))
    assert switch.calls == [
        "authorize artifactr:read_artifacts",
        "authorize artifactr:read_artifacts",
        "authorize artifactr:read_artifacts",
        "authorize artifactr:read_proposals",
        "authorize artifactr:read_events",
        "authorize artifactr:record",
    ]


async def test_each_tenant_has_its_own_switch(storage: Storage, bob: Bob, switch: Switch) -> None:
    workspaces = _workspaces(storage, bob)
    off, on = await _fill(workspaces, "acme"), await _fill(workspaces, "globex")
    _off(switch, "acme")
    with pytest.raises(NotEnabled):
        await off.commit(await _edit(off))
    await on.commit(await _edit(on))
    assert (await on.get(Note, "n1")).data.text == "Send Friday"
    assert (await off.get(Note, "n1")).data.text == "Ship Friday"
    switch.off = {("globex", "w1", NOTES)}
    await off.commit(await _edit(off))
    with pytest.raises(NotEnabled):
        await on.commit(_accept())
    assert (await off.get(Note, "n1")).version == 2
    assert (await on.proposal("p1")).status == "pending"


# ─── the outcome table ───────────────────────────────────────────────────────

GATED: dict[str, bool] = {
    "create": True,
    "edit": True,
    "propose_edit": True,
    "archive": False,
    "accept": True,
    "reject": False,
}
"""Each command Bob may send about n1, or n2 for a new note, and whether off refuses it."""


async def _command(ws: Workspace, name: str) -> Command:
    edit = (await ws.as_actor(ALICE).get(Note, "n1")).edit_text("Ship", "Send")
    match name:
        case "create":
            return create_artifact(Note(text="new"), artifact_id="n2")
        case "edit":
            return edit
        case "propose_edit":
            return ProposeChange(change=edit)
        case "archive":
            return ArchiveArtifact(artifact_id="n1", base_version=1)
        case "accept":
            return _accept()
        case _:
            return RespondToProposal(proposal_id="p1", decision="reject")


async def _outcome(storage: Storage, name: str, *, on: bool, hidden: bool, authorized: bool) -> str:
    switch = Switch()
    bob = Bob(switch)
    ws = await _fill(_workspaces(storage, bob))
    command = await _command(ws, name)
    if not on:
        _off(switch)
    bob.hidden = frozenset({"n1", "n2"} if hidden else ())
    bob.refused = not authorized
    try:
        await ws.commit(command)
    except (NotFound, NotEnabled, Forbidden) as refused:
        return refused.code
    return "applied"


@pytest.mark.parametrize(
    ("name", "on", "hidden", "authorized"),
    list(itertools.product(sorted(GATED), (True, False), (True, False), (True, False))),
)
async def test_missing_beats_off_beats_forbidden(
    storage: Storage, name: str, on: bool, hidden: bool, authorized: bool
) -> None:
    if hidden:
        expected = "not_found"
    elif GATED[name] and not on:
        expected = "not_enabled"
    elif not authorized:
        expected = "forbidden"
    else:
        expected = "applied"
    outcome = await _outcome(storage, name, on=on, hidden=hidden, authorized=authorized)
    assert outcome == expected
