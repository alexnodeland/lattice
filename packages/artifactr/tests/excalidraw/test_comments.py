"""A comment on a diagram's element: feedback, anchored by the element's id, refused where the
diagram's version holds no such element live (lattice RFC-0006, relayr ADR-0041)."""

import pytest

from artifactr.core import (
    ArtifactTarget,
    CreateArtifact,
    EditArtifact,
    FeedbackGiven,
    GiveFeedback,
    ValidationFailed,
)
from artifactr.excalidraw import (
    EXCALIDRAW_TYPES,
    Diagram,
    DiagramComment,
    element_patch,
    excalidraw_checks,
    excalidraw_key_of,
)
from artifactr.workspace import InMemoryStorage, Scope, Workspace, Workspaces, integration_gate
from tests.artifact_types import Note
from tests.excalidraw.scenes import data, element
from tests.ui.people import ALICE
from tests.ui.refusals import locs
from tests.ui.toggles import Toggles


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
async def ws(storage: InMemoryStorage) -> Workspace:
    workspaces = Workspaces(
        storage,
        types=[*EXCALIDRAW_TYPES, Note],
        checks=excalidraw_checks(),
        gate=integration_gate(Toggles(), excalidraw_key_of),
    )
    ws = await workspaces.open("tenant_a", "ws_1", actor=ALICE)
    await ws.commit(
        CreateArtifact(
            kind="excalidraw_diagram", artifact_id="d1", data=data(element("a"), element("b"))
        )
    )
    head = await ws.get(Diagram, "d1")
    gone = head.data.elements["a"].model_copy(update={"version": 2, "is_deleted": True})
    patch = element_patch(head.data, {**head.data.elements, "a": gone})
    await ws.commit(EditArtifact(artifact_id="d1", base_version=1, patch=patch))
    return ws


def _comment(element_id: str, version: int, artifact_id: str = "d1") -> GiveFeedback:
    return GiveFeedback(
        feedback_type=DiagramComment.feedback_type,
        target=ArtifactTarget(artifact_id=artifact_id, version=version),
        value={"element_id": element_id, "text": "make it bigger"},
    )


async def test_a_comment_on_a_live_element_is_given_with_its_anchor(ws: Workspace) -> None:
    await ws.commit(_comment("b", 2))
    [given] = [e.event for e in await ws.read() if isinstance(e.event, FeedbackGiven)]
    assert (given.feedback_type, given.value["element_id"]) == ("diagram_comment", "b")
    # On version 1, "a" was there, live.
    await ws.commit(_comment("a", 1))


@pytest.mark.parametrize(("element_id", "version"), [("a", 2), ("zz", 2), ("zz", 1)])
async def test_a_comment_on_an_element_the_version_doesnt_hold_live_is_refused(
    ws: Workspace, element_id: str, version: int
) -> None:
    with pytest.raises(ValidationFailed, match="holds no element") as refused:
        await ws.commit(_comment(element_id, version))
    assert locs(refused.value) == [["value", "element_id"]]


async def test_a_version_thinned_away_is_read_as_the_head(
    ws: Workspace, storage: InMemoryStorage
) -> None:
    assert await storage.drop_revisions(Scope("tenant_a", "ws_1"), "d1", [1]) == 1
    await ws.commit(_comment("b", 1))
    with pytest.raises(ValidationFailed, match="version 1 is no longer kept, and the head"):
        await ws.commit(_comment("a", 1))


async def test_a_comment_on_an_element_is_on_a_diagram(ws: Workspace) -> None:
    await ws.create(Note(text="hi"), artifact_id="n1")
    with pytest.raises(ValidationFailed, match="on a diagram"):
        await ws.commit(_comment("b", 1, "n1"))
