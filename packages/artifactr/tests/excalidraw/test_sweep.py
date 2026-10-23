"""The tombstone sweep: a deleted element removed a day after it was deleted, by the sweep alone."""

from datetime import UTC, datetime, timedelta

import pytest

from artifactr.core import CreateArtifact, EditArtifact, JsonPatch, ValidationFailed
from artifactr.excalidraw import SWEEPER, Diagram, element_patch, sweep_tombstones
from artifactr.excalidraw.sweep import KEEP
from artifactr.workspace import Workspace, Workspaces
from tests.excalidraw.scenes import data, element
from tests.ui.people import ALICE


async def _drawn(workspaces: Workspaces) -> Workspace:
    ws = await workspaces.open("tenant_a", "ws_1", actor=ALICE)
    await ws.commit(
        CreateArtifact(
            kind="excalidraw_diagram", artifact_id="d1", data=data(element("a"), element("b"))
        )
    )
    head = await ws.get(Diagram, "d1")
    gone = head.data.elements["a"].model_copy(update={"version": 2, "is_deleted": True})
    await ws.commit(
        EditArtifact(
            artifact_id="d1",
            base_version=1,
            patch=element_patch(head.data, {**head.data.elements, "a": gone}),
        )
    )
    return ws


async def test_a_tombstone_a_day_old_is_removed_and_a_fresh_one_kept(
    workspaces: Workspaces,
) -> None:
    ws = await _drawn(workspaces)
    sweeper = ws.as_actor(SWEEPER)
    now = datetime.now(UTC)
    assert await sweep_tombstones(sweeper, now=now) == 0, "deleted just now"
    assert await sweep_tombstones(sweeper, now=now + KEEP + timedelta(minutes=1)) == 1
    head = await ws.get(Diagram, "d1")
    assert set(head.data.elements) == {"b"}
    [*_, last] = await ws.revisions("d1")
    assert last.actor == SWEEPER
    assert await sweep_tombstones(sweeper, now=now + 2 * KEEP) == 0, "nothing left"


async def test_only_the_sweep_removes_and_only_a_tombstone(workspaces: Workspaces) -> None:
    ws = await _drawn(workspaces)
    remove_a = JsonPatch(ops=({"op": "remove", "path": "/elements/a"},))
    with pytest.raises(ValidationFailed, match="never removed"):
        await ws.commit(EditArtifact(artifact_id="d1", base_version=2, patch=remove_a))
    remove_b = JsonPatch(ops=({"op": "remove", "path": "/elements/b"},))
    with pytest.raises(ValidationFailed, match="never removed"):
        await ws.as_actor(SWEEPER).commit(
            EditArtifact(artifact_id="d1", base_version=2, patch=remove_b)
        )


async def test_an_untimed_revision_counts_as_old(workspaces: Workspaces) -> None:
    from artifactr.core import Revision
    from artifactr.excalidraw.sweep import _deleted_before

    gone = element("a", version=2, isDeleted=True)
    untimed = Revision(
        artifact_id="d1",
        version=2,
        kind="excalidraw_diagram",
        data=data(gone),
        actor=ALICE,
    )
    assert _deleted_before(gone, [untimed], datetime.now(UTC))
    assert not _deleted_before(gone, [], datetime.now(UTC))
