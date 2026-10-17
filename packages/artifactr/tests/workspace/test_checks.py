"""The application's checks of commands, before they commit (ADR-0073)."""

import pytest

from artifactr.core import (
    Actor,
    AppEvent,
    Applied,
    Command,
    CreateArtifact,
    Forbidden,
    InvalidState,
    NotFound,
    ProposeChange,
    UserActor,
    ValidationFailed,
)
from artifactr.workspace import Access, Check, Storage, Workspace, Workspaces
from tests.artifact_types import Checklist, Note
from tests.workspace.conftest import ALICE

BOB = UserActor(id="bob", name="Bob")


def refusing(refusal: Exception, seen: list[Command] | None = None) -> Check:
    """A check that raises ``refusal`` for every command, noting each it hears in ``seen``."""

    async def check(workspace: Workspace, command: Command) -> None:
        if seen is not None:
            seen.append(command)
        raise refusal

    return check


@pytest.mark.parametrize(
    "refusal", [ValidationFailed("title is required", []), InvalidState("the form is closed")]
)
async def test_a_check_refuses_a_command_of_its_type_and_nothing_is_written(
    storage: Storage, refusal: Exception
) -> None:
    ws = await Workspaces(storage, checks={"create_artifact": refusing(refusal)}).open(
        "tenant_a", "ws_1", actor=ALICE
    )
    with pytest.raises(type(refusal), match=str(refusal)):
        await ws.create(Note(), artifact_id="n1")
    assert await ws.head_seq() == 0
    await ws.create_thread("a command of another type is not checked")
    assert await ws.head_seq() == 1


async def test_a_check_that_fails_otherwise_fails_the_command_as_an_error(
    storage: Storage,
) -> None:
    broken = refusing(RuntimeError("the schema store is down"))
    ws = await Workspaces(storage, checks={"create_thread": broken}).open(
        "tenant_a", "ws_1", actor=ALICE
    )
    with pytest.raises(RuntimeError, match="the schema store is down"):
        await ws.create_thread()
    assert await ws.head_seq() == 0


async def test_a_check_reads_the_workspace_as_the_commands_actor(storage: Storage) -> None:
    asked: list[tuple[str, str]] = []
    seen: list[tuple[Actor, list[str]]] = []

    async def authorize(
        tenant_id: str, workspace_id: str | None, actor: Actor, access: Access
    ) -> bool:
        asked.append((actor.participant, access.action))
        return True

    async def check(workspace: Workspace, command: Command) -> None:
        notes = await workspace.artifacts(Note)
        seen.append((workspace.actor, [note.id for note in notes]))

    workspaces = Workspaces(storage, checks={"create_artifact": check}, authorize=authorize)
    await (await workspaces.open("tenant_a", "ws_1", actor=ALICE)).create(Note(), artifact_id="n1")
    ws = await workspaces.open("tenant_a", "ws_1", actor=BOB)
    asked.clear()
    assert await ws.create(Note(), artifact_id="n2") == Applied(artifact_id="n2", version=1, seq=2)
    assert seen == [(ALICE, []), (BOB, ["n1"])]
    assert asked == [
        ("user:bob", "artifactr:create_artifact"),
        ("user:bob", "artifactr:read_artifacts"),
    ], "authorize is asked before the check, and the check's read as the actor"


async def test_a_command_refused_before_its_check_never_reaches_it(storage: Storage) -> None:
    seen: list[Command] = []

    async def authorize(
        tenant_id: str, workspace_id: str | None, actor: Actor, access: Access
    ) -> bool:
        return actor != BOB

    check = refusing(InvalidState("unreachable"), seen)
    workspaces = Workspaces(
        storage, types=[Note], checks={"create_artifact": check}, authorize=authorize
    )
    ws = await workspaces.open("tenant_a", "ws_1", actor=ALICE)
    with pytest.raises(Forbidden):
        await ws.as_actor(BOB).create(Note())
    with pytest.raises(NotFound, match="artifact type checklist"):
        await ws.create(Checklist())
    assert seen == []


async def test_a_proposed_change_is_checked_as_propose_change(storage: Storage) -> None:
    seen: list[Command] = []
    create = CreateArtifact(artifact_id="n1", kind="note", data={})
    checks = {
        "create_artifact": refusing(InvalidState("only proposals here")),
        "propose_change": refusing(InvalidState("no proposals"), seen),
    }
    ws = await Workspaces(storage, checks=checks).open("tenant_a", "ws_1", actor=ALICE)
    proposal = ProposeChange(change=create)
    with pytest.raises(InvalidState, match="no proposals"):
        await ws.commit(proposal)
    assert seen == [proposal]
    del checks["propose_change"]
    unchecked = await Workspaces(storage, checks=checks).open("tenant_a", "ws_1", actor=ALICE)
    proposed = await unchecked.commit(ProposeChange(change=create))
    assert proposed.proposal_id, "the change it wraps is not checked under its own type"


async def test_a_fact_is_recorded_unchecked(storage: Storage) -> None:
    seen: list[Command] = []
    check = refusing(InvalidState("unreachable"), seen)
    ws = await Workspaces(storage, checks={"app_event": check}).open(
        "tenant_a", "ws_1", actor=ALICE
    )
    await ws.record(AppEvent(name="exported"))
    assert (await ws.head_seq(), seen) == (1, [])
