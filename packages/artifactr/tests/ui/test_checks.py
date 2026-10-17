"""The checks, on every storage: what a submission, an edit or a proposal may be."""

from typing import Any

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from artifactr.agent import Runner, Session
from artifactr.core import (
    Applied,
    ArchiveArtifact,
    CreateArtifact,
    EditArtifact,
    Forbidden,
    InvalidState,
    JsonPatch,
    NotFound,
    ProposeChange,
    Proposed,
    RespondToProposal,
    SetFocus,
    SystemActor,
    TextEdit,
    TextEdits,
    ValidationFailed,
    VersionConflict,
    Visibility,
)
from artifactr.ui import UI_TYPES, FeatureOff, Submission, submission_id, ui_checks
from artifactr.ui.integrations import DASHBOARDS, DEFAULT_ON, FORMS, MINI_APPS, is_enabled
from artifactr.workspace import Storage, Workspace, Workspaces
from tests.ui.people import ADMIN, ALICE, BOB, agent
from tests.ui.refusals import locs
from tests.ui.toggles import Toggles

SCHEMA = {
    "properties": {
        "choice": {"enum": ["yes", "no"]},
        "note": {"type": "string", "maxLength": 20},
    },
    "required": ["choice"],
}


async def _open(workspaces: Workspaces, tenant: str = "tenant_a") -> Workspace:
    return await workspaces.open(tenant, "ws_1", actor=ALICE)


async def _form(ws: Workspace, submissions: str = "once", **more: Any) -> tuple[str, str]:
    """A form in a new thread, made by the thread's agent for Alice: its thread and its id."""
    thread = await ws.create_thread("Poll")
    data = {"title": "Lunch?", "schema": SCHEMA, "submissions": submissions, **more}
    made = await ws.as_actor(agent(thread.id)).commit(
        CreateArtifact(kind="form", data=data, thread_id=thread.id)
    )
    assert isinstance(made, Applied)
    return thread.id, made.artifact_id


def _submit(
    form_id: str,
    *,
    artifact_id: str | None = None,
    version: int = 1,
    values: Any = None,
    nonce: str | None = None,
    to: str = "form_id",
) -> CreateArtifact:
    data: dict[str, Any] = {to: form_id, "version": version, "values": values or {"choice": "yes"}}
    if nonce is not None:
        data["nonce"] = nonce
    derived = submission_id(form_id) if nonce is None else submission_id(form_id, nonce=nonce)
    return CreateArtifact(kind="submission", artifact_id=artifact_id or derived, data=data)


async def _submissions(ws: Workspace) -> list[Submission]:
    return [s.data for s in await ws.artifacts(Submission)]


# ─── submissions ──────────────────────────────────────────────────────────────


async def test_a_retried_submit_is_one_artifact(workspaces: Workspaces) -> None:
    ws = await _open(workspaces)
    _, form_id = await _form(ws)
    assert isinstance(await ws.commit(_submit(form_id)), Applied)
    with pytest.raises(InvalidState):
        await ws.commit(_submit(form_id))
    assert len(await _submissions(ws)) == 1


async def test_a_once_form_takes_one_submission_from_anyone(workspaces: Workspaces) -> None:
    ws = await _open(workspaces)
    _, form_id = await _form(ws)
    await ws.commit(_submit(form_id))
    with pytest.raises(InvalidState):
        await ws.as_actor(BOB).commit(_submit(form_id, values={"choice": "no"}))


async def test_a_submission_against_an_earlier_version_is_refused_as_changed(
    workspaces: Workspaces,
) -> None:
    ws = await _open(workspaces)
    _, form_id = await _form(ws)
    edit = (await ws.artifact(form_id)).edit(lambda form: setattr(form, "title", "Dinner?"))
    await ws.commit(edit)
    with pytest.raises(InvalidState, match="changed: the submission was made against version 1"):
        await ws.commit(_submit(form_id))
    assert isinstance(await ws.commit(_submit(form_id, version=2)), Applied)


async def test_a_closed_or_archived_form_takes_no_submission(workspaces: Workspaces) -> None:
    ws = await _open(workspaces)
    _, closed = await _form(ws, closed=True)
    with pytest.raises(InvalidState, match="is closed"):
        await ws.commit(_submit(closed))
    _, archived = await _form(ws)
    await ws.commit(ArchiveArtifact(artifact_id=archived, base_version=1))
    with pytest.raises(InvalidState, match="is closed"):
        await ws.commit(_submit(archived, version=2))


async def test_values_that_do_not_fit_are_refused_at_their_field(workspaces: Workspaces) -> None:
    ws = await _open(workspaces)
    _, form_id = await _form(ws)
    with pytest.raises(ValidationFailed) as refused:
        await ws.commit(_submit(form_id, values={"choice": "maybe", "note": "x" * 21}))
    assert locs(refused.value) == [["choice"], ["note"]]


async def test_a_submission_whose_id_is_not_its_derivation_is_refused(
    workspaces: Workspaces,
) -> None:
    ws = await _open(workspaces)
    _, form_id = await _form(ws)
    with pytest.raises(ValidationFailed, match="derived") as refused:
        await ws.commit(_submit(form_id, artifact_id="sub_mine"))
    assert locs(refused.value) == [["artifact_id"]]


async def test_submission_data_that_is_not_a_submission_is_refused(
    workspaces: Workspaces,
) -> None:
    ws = await _open(workspaces)
    with pytest.raises(ValidationFailed, match="invalid submission data"):
        await ws.commit(CreateArtifact(kind="submission", data={"values": {}}))


async def test_a_poll_in_a_shared_thread_takes_one_submission_per_person(
    workspaces: Workspaces,
) -> None:
    ws = await _open(workspaces)
    _, form_id = await _form(ws, "per_person")
    for person in (ALICE, BOB):
        command = _submit(form_id, artifact_id=submission_id(form_id, principal=person.participant))
        await ws.as_actor(person).commit(command)
        with pytest.raises(InvalidState):
            await ws.as_actor(person).commit(command)
    assert len(await _submissions(ws)) == 2
    with pytest.raises(ValidationFailed, match="derived"):
        await ws.as_actor(BOB).commit(
            _submit(form_id, artifact_id=submission_id(form_id, principal=ALICE.participant))
        )


async def test_a_per_person_form_takes_nothing_from_who_acts_for_no_one(
    workspaces: Workspaces,
) -> None:
    ws = await _open(workspaces)
    _, form_id = await _form(ws, "per_person")
    with pytest.raises(Forbidden, match="one submission a person"):
        await ws.as_actor(SystemActor()).commit(_submit(form_id))


async def test_a_form_that_takes_one_takes_no_nonce(workspaces: Workspaces) -> None:
    ws = await _open(workspaces)
    _, form_id = await _form(ws)
    command = _submit(form_id, nonce="n1")
    with pytest.raises(ValidationFailed, match="has no nonce") as refused:
        await ws.commit(command.model_copy(update={"artifact_id": submission_id(form_id)}))
    assert locs(refused.value) == [["data", "nonce"]]


async def test_a_many_form_takes_a_submission_a_nonce(workspaces: Workspaces) -> None:
    ws = await _open(workspaces)
    _, form_id = await _form(ws, "many")
    for nonce in ("n1", "n2"):
        await ws.commit(_submit(form_id, nonce=nonce))
    with pytest.raises(ValidationFailed, match="nonce") as refused:
        await ws.commit(_submit(form_id))
    assert locs(refused.value) == [["data", "nonce"]]
    assert len(await _submissions(ws)) == 2


async def test_a_form_the_submitter_cannot_read_is_not_found(storage: Storage) -> None:
    hidden: set[str] = set()

    async def hide(tenant: str, workspace: str, actor: Any) -> Visibility:
        return Visibility(artifacts=frozenset(hidden) if actor == BOB else frozenset())

    workspaces = Workspaces(storage, types=UI_TYPES, checks=ui_checks(), hidden=hide)
    ws = await _open(workspaces)
    _, form_id = await _form(ws)
    hidden.add(form_id)
    with pytest.raises(NotFound):
        await ws.as_actor(BOB).commit(_submit(form_id))


async def test_a_tenant_reads_nothing_of_another_tenants_forms(workspaces: Workspaces) -> None:
    ours = await _open(workspaces)
    _, form_id = await _form(ours)
    theirs = await _open(workspaces, "tenant_b")
    with pytest.raises(NotFound):
        await theirs.commit(_submit(form_id))
    assert await theirs.artifacts() == []
    assert len(await ours.artifacts()) == 1


async def test_a_submission_to_an_app_carries_its_nonce(workspaces: Workspaces) -> None:
    ws = await _open(workspaces)
    thread = await ws.create_thread("Calc")
    app: dict[str, Any] = {"title": "Calc", "summary": "A calculator", "html": "<p>1+1</p>"}
    made = await ws.as_actor(agent(thread.id)).commit(CreateArtifact(kind="app", data=app))
    assert isinstance(made, Applied)
    await ws.commit(_submit(made.artifact_id, nonce="n1", to="app_id", values={"sum": 2}))
    with pytest.raises(ValidationFailed, match="nonce"):
        await ws.commit(_submit(made.artifact_id, to="app_id"))


async def test_other_kinds_are_created_unchecked(workspaces: Workspaces) -> None:
    ws = await _open(workspaces)
    _, form_id = await _form(ws)
    assert (await ws.artifact(form_id)).kind == "form"


# ─── edits ────────────────────────────────────────────────────────────────────


def _set(artifact_id: str, path: str, value: Any, version: int = 1) -> EditArtifact:
    patch = JsonPatch(ops=({"op": "replace", "path": path, "value": value},))
    return EditArtifact(artifact_id=artifact_id, base_version=version, patch=patch)


async def test_no_one_edits_a_submission(workspaces: Workspaces) -> None:
    ws = await _open(workspaces)
    thread_id, form_id = await _form(ws)
    await ws.commit(_submit(form_id))
    edit = _set(submission_id(form_id), "/values/choice", "no")
    for actor in (ALICE, BOB, ADMIN, agent(thread_id)):
        with pytest.raises(Forbidden, match="never edited"):
            await ws.as_actor(actor).commit(edit)


async def test_only_a_forms_author_or_an_admin_closes_it_or_changes_its_schema(
    workspaces: Workspaces,
) -> None:
    ws = await _open(workspaces)
    thread_id, form_id = await _form(ws)
    with pytest.raises(Forbidden, match="author, or an admin"):
        await ws.as_actor(BOB).commit(_set(form_id, "/closed", True))
    with pytest.raises(Forbidden):
        await ws.as_actor(BOB).commit(_set(form_id, "/schema/required", []))
    with pytest.raises(Forbidden):
        await ws.as_actor(BOB).commit(_set(form_id, "/submissions", "many"))
    await ws.as_actor(BOB).commit(_set(form_id, "/title", "Lunch, Friday?"))
    await ws.as_actor(ALICE).commit(_set(form_id, "/closed", True, version=2))
    await ws.as_actor(agent(thread_id, run_id="run_2")).commit(_set(form_id, "/closed", False, 3))
    await ws.as_actor(ADMIN).commit(_set(form_id, "/closed", True, version=4))


async def test_a_form_made_by_a_run_for_no_one_is_governed_by_that_agent_alone(
    workspaces: Workspaces,
) -> None:
    ws = await _open(workspaces)
    thread = await ws.create_thread("Rules")
    rules = agent(thread.id, acting_for=None)
    data = {"title": "Ack", "schema": {}}
    made = await ws.as_actor(rules).commit(CreateArtifact(kind="form", data=data))
    assert isinstance(made, Applied)
    with pytest.raises(Forbidden):
        await ws.as_actor(SystemActor()).commit(_set(made.artifact_id, "/closed", True))
    await ws.as_actor(rules).commit(_set(made.artifact_id, "/closed", True))


async def test_a_stale_edit_is_left_to_artifactr(workspaces: Workspaces) -> None:
    ws = await _open(workspaces)
    _, form_id = await _form(ws)
    await ws.commit(_set(form_id, "/title", "Dinner?"))
    with pytest.raises(VersionConflict):
        await ws.as_actor(BOB).commit(_set(form_id, "/closed", True))


async def test_a_person_changes_only_an_apps_state(workspaces: Workspaces) -> None:
    ws = await _open(workspaces)
    thread = await ws.create_thread("Calc")
    app: dict[str, Any] = {"title": "Calc", "summary": "A calculator", "html": "<p>0</p>"}
    made = await ws.as_actor(agent(thread.id)).commit(CreateArtifact(kind="app", data=app))
    assert isinstance(made, Applied)
    app_id = made.artifact_id
    await ws.commit(_set(app_id, "/state", {"total": 1}))
    with pytest.raises(Forbidden, match="only app"):
        await ws.commit(_set(app_id, "/html", "<script>", version=2))
    text = TextEdits(field="html", edits=(TextEdit(old="0", new="1"),))
    with pytest.raises(Forbidden):
        await ws.commit(EditArtifact(artifact_id=app_id, base_version=2, patch=text))
    await ws.as_actor(agent(thread.id)).commit(_set(app_id, "/html", "<p>2</p>", version=2))


async def test_other_kinds_are_edited_unchecked(workspaces: Workspaces) -> None:
    ws = await _open(workspaces)
    thread = await ws.create_thread("Ops")
    data = {"title": "Ops", "panels": [], "as_of": "2026-10-17T00:00:00Z"}
    made = await ws.as_actor(agent(thread.id)).commit(CreateArtifact(kind="dashboard", data=data))
    assert isinstance(made, Applied)
    assert isinstance(
        await ws.as_actor(BOB).commit(_set(made.artifact_id, "/title", "Ops!")), Applied
    )


# ─── proposals ────────────────────────────────────────────────────────────────


async def test_a_proposed_change_is_checked_as_the_change(workspaces: Workspaces) -> None:
    ws = await _open(workspaces)
    thread_id, form_id = await _form(ws)
    with pytest.raises(Forbidden, match="never proposed"):
        await ws.commit(ProposeChange(change=_submit(form_id)))
    with pytest.raises(Forbidden):
        await ws.as_actor(BOB).commit(ProposeChange(change=_set(form_id, "/closed", True)))
    archive = ArchiveArtifact(artifact_id=form_id, base_version=1)
    with pytest.raises(Forbidden):
        await ws.as_actor(BOB).commit(ProposeChange(change=archive))
    app = CreateArtifact(kind="app", data={"title": "A", "summary": "S", "html": "<p></p>"})
    with pytest.raises(Forbidden, match="an app is an agent's"):
        await ws.as_actor(BOB).commit(ProposeChange(change=app))
    proposed = await ws.as_actor(agent(thread_id)).commit(ProposeChange(change=app))
    assert isinstance(proposed, Proposed)


async def _proposal(storage: Storage, change: Any, *, by: Any = BOB) -> str:
    """A proposal made past the checks, as one made before an application registered them."""
    unchecked = await Workspaces(storage, types=UI_TYPES).open("tenant_a", "ws_1", actor=by)
    proposed = await unchecked.commit(ProposeChange(change=change))
    return proposed.proposal_id


async def test_an_accepted_change_is_checked_again_as_its_proposer_on_the_head(
    storage: Storage, workspaces: Workspaces
) -> None:
    ws = await _open(workspaces)
    _, form_id = await _form(ws)
    closing = await _proposal(storage, _set(form_id, "/closed", True))
    await ws.commit(_set(form_id, "/title", "Dinner?"))
    with pytest.raises(Forbidden, match="author, or an admin"):
        await ws.commit(RespondToProposal(proposal_id=closing, decision="accept"))
    sending = await _proposal(storage, _submit(form_id, version=2), by=ALICE)
    with pytest.raises(Forbidden, match="never proposed"):
        await ws.as_actor(BOB).commit(RespondToProposal(proposal_id=sending, decision="accept"))
    rejected = await ws.commit(RespondToProposal(proposal_id=closing, decision="reject"))
    assert rejected.decision == "reject"
    with pytest.raises(InvalidState):
        await ws.commit(RespondToProposal(proposal_id=closing, decision="accept"))


async def test_a_reviewer_takes_no_changes_of_their_own_on_a_form(
    storage: Storage, workspaces: Workspaces
) -> None:
    ws = await _open(workspaces)
    thread_id, form_id = await _form(ws)
    retitle = await _proposal(storage, _set(form_id, "/title", "Brunch?"), by=agent(thread_id))
    own = JsonPatch(ops=({"op": "replace", "path": "/closed", "value": True},))
    with pytest.raises(Forbidden, match="without changes"):
        await ws.as_actor(BOB).commit(
            RespondToProposal(proposal_id=retitle, decision="accept", changes=own)
        )
    accepted = await ws.as_actor(BOB).commit(
        RespondToProposal(proposal_id=retitle, decision="accept")
    )
    assert accepted.version == 2
    dashboard = {"title": "Ops", "panels": [], "as_of": "2026-10-17T00:00:00Z"}
    showing = await _proposal(
        storage, CreateArtifact(kind="dashboard", data=dashboard), by=agent(thread_id)
    )
    retitled = JsonPatch(ops=({"op": "replace", "path": "/title", "value": "Ops!"},))
    shown = await ws.commit(
        RespondToProposal(proposal_id=showing, decision="accept", changes=retitled)
    )
    assert shown.version == 1


async def test_only_an_author_or_an_admin_archives_a_form_or_a_submission(
    workspaces: Workspaces,
) -> None:
    ws = await _open(workspaces)
    _, form_id = await _form(ws)
    sub = submission_id(form_id)
    await ws.as_actor(BOB).commit(_submit(form_id))
    with pytest.raises(Forbidden, match="archives it"):
        await ws.commit(ArchiveArtifact(artifact_id=sub, base_version=1))
    with pytest.raises(Forbidden, match="archives it"):
        await ws.as_actor(BOB).commit(ArchiveArtifact(artifact_id=form_id, base_version=1))
    await ws.as_actor(ADMIN).commit(ArchiveArtifact(artifact_id=sub, base_version=1))
    await ws.commit(ArchiveArtifact(artifact_id=form_id, base_version=1))
    thread = await ws.create_thread("Ops")
    data = {"title": "Ops", "panels": [], "as_of": "2026-10-17T00:00:00Z"}
    made = await ws.as_actor(agent(thread.id)).commit(CreateArtifact(kind="dashboard", data=data))
    assert isinstance(made, Applied)
    await ws.as_actor(BOB).commit(ArchiveArtifact(artifact_id=made.artifact_id, base_version=1))


async def test_a_person_makes_no_app(workspaces: Workspaces) -> None:
    ws = await _open(workspaces)
    app: dict[str, Any] = {"title": "Calc", "summary": "A calculator", "html": "<p>1</p>"}
    with pytest.raises(Forbidden, match="an app is an agent's"):
        await ws.commit(CreateArtifact(kind="app", data=app))


async def test_a_refusal_of_a_stale_or_closed_submission_says_why_on_every_surface(
    workspaces: Workspaces,
) -> None:
    ws = await _open(workspaces)
    _, form_id = await _form(ws)
    await ws.commit(_set(form_id, "/title", "Dinner?"))
    runner = Runner(Agent(TestModel(), deps_type=Session[None]), app=None)
    changed = await runner.execute(ws, _submit(form_id), command_id="c1")
    assert changed.rejection == {
        "type": "invalid_state",
        "message": f"form {form_id} changed: the submission was made against version 1, and it "
        "is at 2",
        "reason": "changed",
        "artifact_id": form_id,
        "version": 1,
        "head": 2,
    }
    await ws.commit(_set(form_id, "/closed", True, version=2))
    closed = await runner.execute(ws, _submit(form_id, version=3), command_id="c2")
    assert closed.rejection is not None
    assert (closed.rejection["reason"], closed.rejection["artifact_id"]) == ("closed", form_id)
    await runner.aclose()


async def test_a_check_is_called_with_its_own_type_alone(workspaces: Workspaces) -> None:
    ws = await _open(workspaces)
    for check in ui_checks().values():
        await check(ws, SetFocus(thread_id="t", artifact_ids=()))


# ─── features switched off ────────────────────────────────────────────────────


async def test_a_feature_switched_off_in_a_workspace_takes_no_new_commands(
    storage: Storage,
) -> None:
    toggles = Toggles()
    workspaces = Workspaces(storage, types=UI_TYPES, checks=ui_checks(integrations=toggles))
    ws = await workspaces.open("tenant_a", "ws_1", actor=ALICE)
    _, form_id = await _form(ws)
    thread = await ws.create_thread("Ops")
    data = {"title": "Ops", "panels": [], "as_of": "2026-10-17T00:00:00Z"}
    run = ws.as_actor(agent(thread.id))
    made = await run.commit(CreateArtifact(kind="dashboard", data=data))
    assert isinstance(made, Applied)
    toggles.off["ws_1"] = {FORMS, DASHBOARDS}
    refusals = [
        _submit(form_id),
        CreateArtifact(kind="form", data={"title": "Again?", "schema": SCHEMA}),
        CreateArtifact(kind="dashboard", data=data),
        _set(made.artifact_id, "/title", "Ops!"),
    ]
    for command in refusals:
        with pytest.raises(FeatureOff) as refused:
            await run.commit(command)
        assert refused.value.payload()["reason"] == "off"
        assert refused.value.payload()["key"] in {FORMS, DASHBOARDS}
    assert {a.kind for a in await ws.artifacts()} == {"form", "dashboard"}, "what exists reads"
    await ws.commit(_set(form_id, "/closed", True))  # its author still closes a form
    other = await workspaces.open("tenant_a", "ws_2", actor=ALICE)
    assert isinstance(await other.commit(CreateArtifact(kind="dashboard", data=data)), Applied)


async def test_without_integrations_forms_and_dashboards_are_on_and_mini_apps_off() -> None:
    assert {FORMS, DASHBOARDS} == DEFAULT_ON
    assert [await is_enabled(None, "t", "w", key) for key in (FORMS, DASHBOARDS, MINI_APPS)] == [
        True,
        True,
        False,
    ]
    assert str(FeatureOff(MINI_APPS)) == "mini apps are off in this workspace"
