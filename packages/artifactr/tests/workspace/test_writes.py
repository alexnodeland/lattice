"""Which kinds an agent's writes apply to directly in Auto: ``agent-writes:direct`` (ADR-0009)."""

from collections.abc import Mapping

import pytest

from artifactr.core import (
    AgentActor,
    Applied,
    Artifact,
    ProposeChange,
    Proposed,
    SetThreadMode,
    UserActor,
)
from artifactr.excalidraw import Diagram
from artifactr.files import Presentation, WordDocument, Workbook
from artifactr.workspace import (
    DIRECT_WRITES,
    InMemoryStorage,
    Workspace,
    Workspaces,
    direct_writes,
    direct_writes_from,
)
from lattice_core.settings import SettingsDefaults, Value, registry
from tests.artifact_types import Checklist, Note

ALICE = UserActor(id="alice", name="Alice")
TYPES: tuple[type[Artifact], ...] = (Note, Checklist)
SETTING = direct_writes(TYPES)


class Layered:
    """A store's answers: the default, narrowed by each workspace's own value."""

    def __init__(self, values: Mapping[str, Value]) -> None:
        self._values = values

    async def value(self, _tenant_id: str, workspace_id: str, key: str, /) -> Value:
        assert key == DIRECT_WRITES
        return SETTING.narrow(SETTING.default, self._values.get(workspace_id))


async def _agent(workspaces: Workspaces, *, mode: str = "edit") -> tuple[Workspace, Workspace]:
    ws = await workspaces.open("t", "w", actor=ALICE)
    thread = await ws.create_thread("Plan")
    if mode == "suggest":
        await ws.commit(SetThreadMode(thread_id=thread.id, mode="suggest"))
    await ws.create(Note(text="Friday"), artifact_id="n1")
    await ws.create(Checklist(), artifact_id="c1")
    return ws, ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_1"))


async def _outcomes(agent: Workspace) -> tuple[type, type]:
    note = (await agent.get(Note, "n1")).edit_text("Friday", "Monday")
    checklist = (await agent.get(Checklist, "c1")).edit(lambda c: setattr(c, "title", "Launch"))
    return type(await agent.commit(note)), type(await agent.commit(checklist))


def test_the_default_is_each_kinds_write_policy() -> None:
    assert SETTING.key == DIRECT_WRITES
    assert SETTING.default == ("note",)
    assert SETTING.labels == {"note": "applies by default", "checklist": "reviewed by default"}


def test_the_kinds_that_propose_today_still_do_by_default() -> None:
    reviewed = (Diagram, WordDocument, Presentation, Workbook)
    assert direct_writes((Note, *reviewed)).default == ("note",)


@pytest.mark.parametrize("hook", [False, True])
async def test_by_default_nothing_changes(hook: bool) -> None:
    known = registry(SETTING)
    direct = direct_writes_from(SettingsDefaults(known)) if hook else None
    workspaces = Workspaces(InMemoryStorage(), direct_writes=direct)
    _, agent = await _agent(workspaces)
    assert await _outcomes(agent) == (Applied, Proposed)


async def test_ask_proposes_every_kind_even_those_the_operator_lets_apply() -> None:
    defaults = SettingsDefaults(registry(SETTING), operator={DIRECT_WRITES: ["checklist", "note"]})
    workspaces = Workspaces(InMemoryStorage(), direct_writes=direct_writes_from(defaults))
    _, auto = await _agent(workspaces)
    assert await _outcomes(auto) == (Applied, Applied)
    _, ask = await _agent(
        Workspaces(InMemoryStorage(), direct_writes=direct_writes_from(defaults)), mode="suggest"
    )
    assert await _outcomes(ask) == (Proposed, Proposed)


async def test_a_kind_taken_out_waits_for_review_in_auto() -> None:
    workspaces = Workspaces(InMemoryStorage(), direct_writes=direct_writes_from(Layered({"w": ()})))
    ws, agent = await _agent(workspaces)
    assert await _outcomes(agent) == (Proposed, Proposed)
    note = (await ws.get(Note, "n1")).edit_text("Friday", "Monday")
    assert isinstance(await ws.commit(note), Applied), "a person's edit still applies"


def test_a_layer_below_cant_put_back_what_one_above_took_out() -> None:
    assert not SETTING.within(("checklist", "note"), ("note",))
    assert SETTING.narrow((), ("note",)) == ()


async def test_a_value_that_isnt_names_fails_the_write() -> None:
    class Numbers:
        async def value(self, *_: str) -> Value:
            return 3

    workspaces = Workspaces(InMemoryStorage(), direct_writes=direct_writes_from(Numbers()))
    _, agent = await _agent(workspaces)
    note = (await agent.get(Note, "n1")).edit_text("Friday", "Monday")
    with pytest.raises(TypeError, match="agent-writes:direct holds names"):
        await agent.commit(note)
    proposed = await agent.commit(ProposeChange(change=note))
    assert isinstance(proposed, Proposed), "a proposal never asks"
