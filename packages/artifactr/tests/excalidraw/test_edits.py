"""RFC-0006's exit criteria for a diagram's data, on every storage: proposals on different
elements both accept, on the same element the second fails, a stale direct edit rebases, and an
element's version only grows."""

import pytest

from artifactr.core import (
    Applied,
    CreateArtifact,
    EditArtifact,
    JsonPatch,
    NotEnabled,
    PatchFailed,
    ProposeChange,
    Proposed,
    RespondToProposal,
    TextEdit,
    TextEdits,
    ValidationFailed,
    VersionConflict,
)
from artifactr.excalidraw import EXCALIDRAW, Diagram, element_patch, rebase
from artifactr.workspace import Workspace, Workspaces
from tests.excalidraw.scenes import data, diagram, element, moved
from tests.ui.people import ALICE, BOB, agent
from tests.ui.toggles import Toggles

R1, R2 = element("r1"), element("r2")


async def _drawn(workspaces: Workspaces) -> tuple[Workspace, str]:
    ws = await workspaces.open("tenant_a", "ws_1", actor=ALICE)
    made = await ws.commit(CreateArtifact(kind="excalidraw_diagram", data=data(R1, R2)))
    assert isinstance(made, Applied)
    return ws, made.artifact_id


async def _head(ws: Workspace, artifact_id: str) -> tuple[int, Diagram]:
    head = await ws.get(Diagram, artifact_id)
    return head.version, head.data


async def _propose(ws: Workspace, artifact_id: str, *moves: tuple[str, float]) -> str:
    """The thread's agent proposes moving elements, against the head it read."""
    thread = await ws.create_thread("Tidy")
    version, head = await _head(ws, artifact_id)
    after = dict(head.elements)
    for key, x in moves:
        after[key] = moved(head.elements[key], x)
    proposed = await ws.as_actor(agent(thread.id)).commit(
        EditArtifact(
            artifact_id=artifact_id,
            base_version=version,
            patch=element_patch(head, after),
            thread_id=thread.id,
        )
    )
    assert isinstance(proposed, Proposed), "an agent proposes a diagram's changes by default"
    return proposed.proposal_id


async def test_two_proposals_on_different_elements_both_accept(workspaces: Workspaces) -> None:
    ws, artifact_id = await _drawn(workspaces)
    first = await _propose(ws, artifact_id, ("r1", 100))
    second = await _propose(ws, artifact_id, ("r2", 200))
    await ws.commit(RespondToProposal(proposal_id=first, decision="accept"))
    await ws.commit(RespondToProposal(proposal_id=second, decision="accept"))
    _, head = await _head(ws, artifact_id)
    assert (head.elements["r1"].model_extra or {})["x"] == 100
    assert (head.elements["r2"].model_extra or {})["x"] == 200


async def test_a_second_proposal_on_the_same_element_fails_whole(workspaces: Workspaces) -> None:
    ws, artifact_id = await _drawn(workspaces)
    first = await _propose(ws, artifact_id, ("r1", 100))
    second = await _propose(ws, artifact_id, ("r1", 300), ("r2", 300))
    await ws.commit(RespondToProposal(proposal_id=first, decision="accept"))
    with pytest.raises(PatchFailed):
        await ws.commit(RespondToProposal(proposal_id=second, decision="accept"))
    _, head = await _head(ws, artifact_id)
    assert (head.elements["r2"].model_extra or {})["x"] == 0, "nothing of it applied"


async def test_a_stale_direct_edit_conflicts_then_rebases(workspaces: Workspaces) -> None:
    ws, artifact_id = await _drawn(workspaces)
    version, base = await _head(ws, artifact_id)
    # Bob moves r1, while Alice, from the same base, moves r1 and r2.
    bobs = {**base.elements, "r1": moved(base.elements["r1"], 50, nonce=5)}
    await ws.as_actor(BOB).commit(
        EditArtifact(artifact_id=artifact_id, base_version=version, patch=element_patch(base, bobs))
    )
    alices = {
        **base.elements,
        "r1": moved(base.elements["r1"], 70, nonce=9),
        "r2": moved(base.elements["r2"], 90),
    }
    stale = EditArtifact(
        artifact_id=artifact_id, base_version=version, patch=element_patch(base, alices)
    )
    with pytest.raises(VersionConflict):
        await ws.commit(stale)
    head_version, head = await _head(ws, artifact_id)
    rebased = rebase(base, alices, head)
    await ws.commit(
        EditArtifact(
            artifact_id=artifact_id,
            base_version=head_version,
            patch=element_patch(head, rebased),
        )
    )
    _, final = await _head(ws, artifact_id)
    # At one version each, Bob's lower nonce won r1, as every canvas reconciling would decide.
    assert (final.elements["r1"].model_extra or {})["x"] == 50
    assert (final.elements["r2"].model_extra or {})["x"] == 90


async def test_a_rebase_that_wins_sends_its_element_above_the_head(workspaces: Workspaces) -> None:
    ws, artifact_id = await _drawn(workspaces)
    version, base = await _head(ws, artifact_id)
    bobs = {**base.elements, "r1": moved(base.elements["r1"], 50, nonce=30)}
    await ws.as_actor(BOB).commit(
        EditArtifact(artifact_id=artifact_id, base_version=version, patch=element_patch(base, bobs))
    )
    head_version, head = await _head(ws, artifact_id)
    alices = {**base.elements, "r1": moved(base.elements["r1"], 70, nonce=1)}
    rebased = rebase(base, alices, head)
    assert rebased["r1"].version == head.elements["r1"].version + 1
    await ws.commit(
        EditArtifact(
            artifact_id=artifact_id, base_version=head_version, patch=element_patch(head, rebased)
        )
    )
    _, final = await _head(ws, artifact_id)
    assert (final.elements["r1"].model_extra or {})["x"] == 70


async def test_a_version_that_doesnt_grow_is_refused(workspaces: Workspaces) -> None:
    ws, artifact_id = await _drawn(workspaces)
    version, head = await _head(ws, artifact_id)
    same = head.elements["r1"].model_copy(update={"x": 5})
    patch = element_patch(head, {**head.elements, "r1": same})
    with pytest.raises(ValidationFailed, match="version must grow"):
        await ws.commit(EditArtifact(artifact_id=artifact_id, base_version=version, patch=patch))


async def test_an_add_of_an_element_that_exists_is_refused(workspaces: Workspaces) -> None:
    ws, artifact_id = await _drawn(workspaces)
    version, _ = await _head(ws, artifact_id)
    patch = JsonPatch(
        ops=(
            {
                "op": "add",
                "path": "/elements/r1",
                "value": element("r1", version=9).model_dump(mode="json"),
            },
        )
    )
    with pytest.raises(ValidationFailed, match="exists"):
        await ws.commit(EditArtifact(artifact_id=artifact_id, base_version=version, patch=patch))


async def test_an_image_is_added_never_replaced(workspaces: Workspaces) -> None:
    ws, artifact_id = await _drawn(workspaces)
    digest = "a" * 64
    image = {"sha256": digest, "size": 3, "media_type": "image/png"}
    version, _ = await _head(ws, artifact_id)
    add = JsonPatch(ops=({"op": "add", "path": f"/files/{digest}", "value": image},))
    await ws.commit(EditArtifact(artifact_id=artifact_id, base_version=version, patch=add))
    replace = JsonPatch(
        ops=({"op": "replace", "path": f"/files/{digest}", "value": {**image, "size": 4}},)
    )
    with pytest.raises(ValidationFailed, match="never replaced"):
        await ws.commit(
            EditArtifact(artifact_id=artifact_id, base_version=version + 1, patch=replace)
        )


async def test_a_proposal_whose_version_doesnt_grow_is_refused(workspaces: Workspaces) -> None:
    ws, artifact_id = await _drawn(workspaces)
    thread = await ws.create_thread("Tidy")
    version, head = await _head(ws, artifact_id)
    same = head.elements["r1"].model_copy(update={"x": 5})
    with pytest.raises(ValidationFailed, match="version must grow"):
        await ws.as_actor(agent(thread.id)).commit(
            EditArtifact(
                artifact_id=artifact_id,
                base_version=version,
                patch=element_patch(head, {**head.elements, "r1": same}),
                thread_id=thread.id,
            )
        )


async def test_off_refuses_changes_and_keeps_diagrams_readable(
    workspaces: Workspaces, toggles: Toggles
) -> None:
    ws, artifact_id = await _drawn(workspaces)
    toggles.off["ws_1"] = {EXCALIDRAW}
    version, head = await _head(ws, artifact_id)
    with pytest.raises(NotEnabled):
        await ws.commit(
            EditArtifact(
                artifact_id=artifact_id,
                base_version=version,
                patch=element_patch(head, {**head.elements, "r1": moved(head.elements["r1"], 1)}),
            )
        )
    with pytest.raises(NotEnabled):
        await ws.commit(CreateArtifact(kind="excalidraw_diagram", data=diagram().to_json()))
    assert (await ws.get(Diagram, artifact_id)).version == version


async def test_rejecting_and_proposing_a_new_diagram_are_left_to_artifactr(
    workspaces: Workspaces,
) -> None:
    ws, artifact_id = await _drawn(workspaces)
    proposal = await _propose(ws, artifact_id, ("r1", 100))
    await ws.commit(RespondToProposal(proposal_id=proposal, decision="reject"))
    thread = await ws.create_thread("New")
    new = await ws.as_actor(agent(thread.id)).commit(
        CreateArtifact(kind="excalidraw_diagram", data=data(R1), thread_id=thread.id)
    )
    assert isinstance(new, Proposed)
    await ws.commit(RespondToProposal(proposal_id=new.proposal_id, decision="accept"))


async def test_renaming_with_text_edits_changes_no_element(workspaces: Workspaces) -> None:
    ws, artifact_id = await _drawn(workspaces)
    version, _ = await _head(ws, artifact_id)
    rename = TextEdits(field="name", edits=(TextEdit(old="Plan", new="Design"),))
    await ws.commit(EditArtifact(artifact_id=artifact_id, base_version=version, patch=rename))
    assert (await _head(ws, artifact_id))[1].name == "Design"


async def test_an_element_put_under_another_key_is_refused_as_core_would(
    workspaces: Workspaces,
) -> None:
    ws, artifact_id = await _drawn(workspaces)
    version, _ = await _head(ws, artifact_id)
    wrong = JsonPatch(
        ops=({"op": "add", "path": "/elements/n2", "value": element("n1").model_dump(mode="json")},)
    )
    with pytest.raises(ValidationFailed):
        await ws.commit(EditArtifact(artifact_id=artifact_id, base_version=version, patch=wrong))


async def test_an_image_is_never_removed(workspaces: Workspaces) -> None:
    ws, artifact_id = await _drawn(workspaces)
    version, _ = await _head(ws, artifact_id)
    remove = JsonPatch(ops=({"op": "remove", "path": f"/files/{'d' * 64}"},))
    with pytest.raises(ValidationFailed, match="never replaced or removed"):
        await ws.commit(EditArtifact(artifact_id=artifact_id, base_version=version, patch=remove))


async def test_a_persons_proposal_is_held_to_the_same_rules(workspaces: Workspaces) -> None:
    ws, artifact_id = await _drawn(workspaces)
    version, head = await _head(ws, artifact_id)
    same = head.elements["r1"].model_copy(update={"x": 5})
    change = EditArtifact(
        artifact_id=artifact_id,
        base_version=version,
        patch=element_patch(head, {**head.elements, "r1": same}),
    )
    with pytest.raises(ValidationFailed, match="version must grow"):
        await ws.as_actor(BOB).commit(ProposeChange(change=change))
