"""relayr.excalidraw: each commit to a diagram reaches a rule once, as the elements it changed;
a comment on an element reaches one with its anchor (lattice RFC-0006, relayr ADR-0041)."""

import asyncio
from contextlib import aclosing
from typing import Any

import pytest
from pydantic import JsonValue

import artifactr
import artifactr.core as a
import reflexr
import reflexr.core
import reflexr.workspace as r
from artifactr.core import (
    ArchiveArtifact,
    ArtifactTarget,
    CreateArtifact,
    EditArtifact,
    GiveFeedback,
    JsonPatch,
)
from artifactr.excalidraw import (
    EXCALIDRAW_TYPES,
    Diagram,
    DiagramComment,
    Element,
    element_patch,
    excalidraw_checks,
)
from relayr.events import BRIDGED, ArtifactArchived, FeedbackGiven, Projections
from relayr.excalidraw import (
    EXCALIDRAW_EVENTS,
    EXCALIDRAW_PROJECTIONS,
    EXCALIDRAW_PUBLISHERS,
    MAX_LABEL,
    ElementsChanged,
    ElementTouched,
)
from relayr.inbound import SOURCE, Followers
from relayr.ledger import Ledger
from tests.events.test_events import envelope

ALICE = a.UserActor(id="alice", name="Alice")
TENANT, WORKSPACE = "acme", "prod"


def _element(key: str, version: int = 1, **fields: Any) -> Element:
    return Element.model_validate(
        {"id": key, "type": "rectangle", "version": version, "versionNonce": version, **fields}
    )


def _patched(*ops: dict[str, JsonValue]) -> a.ArtifactChanged:
    return a.ArtifactChanged(
        artifact_id="d1", kind=Diagram.kind, version=3, patch=JsonPatch(ops=ops), summary="s"
    )


def _project(event: Any) -> reflexr.Event | None:
    return Projections(**EXCALIDRAW_PROJECTIONS).project(envelope(event, thread_id="t1"))


def test_a_diagram_made_is_its_live_elements_added_with_their_labels() -> None:
    diagram = Diagram(
        name="Stack",
        elements={
            "box": _element("box"),
            "label": _element("label", type="text", text="API", containerId="box"),
            "frame": _element("frame", type="frame", name="Backend"),
            "gone": _element("gone", 2, isDeleted=True),
        },
    )
    made = a.ArtifactCreated(artifact_id="d1", kind=Diagram.kind, version=1, data=diagram.to_json())
    projected = _project(made)
    assert isinstance(projected, ElementsChanged)
    assert projected.event_type == "excalidraw:elements_changed"
    assert projected.added == (
        ElementTouched(id="box", label="API"),
        ElementTouched(id="label", label="API"),
        ElementTouched(id="frame", label="Backend"),
    )
    assert (projected.diagram_id, projected.thread_id, projected.author) == (
        "d1",
        "t1",
        a.UserActor(id="alice"),
    )


def test_a_commit_is_what_it_added_changed_and_removed() -> None:
    ops: tuple[dict[str, JsonValue], ...] = (
        {"op": "test", "path": "/elements/b/version", "value": 1},
        {
            "op": "replace",
            "path": "/elements/b",
            "value": {"id": "b", "type": "text", "text": "DB"},
        },
        {"op": "add", "path": "/elements/c", "value": {"id": "c", "type": "ellipse"}},
        {"op": "replace", "path": "/elements/a", "value": {"id": "a", "isDeleted": True}},
        {"op": "remove", "path": "/elements/t"},
        {"op": "copy", "from": "/elements/a", "path": "/elements/z"},  # none a writer sends
        {"op": "add", "path": "/files/" + "f" * 64, "value": {}},
    )
    changed = a.ArtifactChanged(
        artifact_id="d1",
        kind=Diagram.kind,
        version=4,
        patch=JsonPatch(ops=ops),
        summary="moved things",
    )
    projected = _project(changed)
    assert isinstance(projected, ElementsChanged)
    assert projected.added == (ElementTouched(id="c"),)
    assert projected.changed == (ElementTouched(id="b", label="DB"),)
    assert projected.removed == (ElementTouched(id="a"), ElementTouched(id="t"))
    assert (projected.version, projected.summary) == (4, "moved things")


def test_labels_are_bounded_and_a_bound_text_wins_over_a_name() -> None:
    long = "x" * (MAX_LABEL * 3)
    ops: tuple[dict[str, JsonValue], ...] = (
        {
            "op": "add",
            "path": "/elements/t",
            "value": {"type": "text", "text": "In", "containerId": "box"},
        },
        {"op": "add", "path": "/elements/box", "value": {"type": "rectangle", "name": "Box"}},
        {"op": "add", "path": "/elements/w", "value": {"type": "text", "text": long}},
    )
    projected = _project(_patched(*ops))
    assert isinstance(projected, ElementsChanged)
    labels = {touched.id: touched.label for touched in projected.added}
    assert labels["box"] == "In", "the text bound in it, though its name came after"
    assert labels["w"] == "x" * (MAX_LABEL - 1) + "\u2026"
    assert len(labels["w"] or "") == MAX_LABEL


def test_an_element_is_named_once_by_the_last_op_on_it_and_odd_paths_pass() -> None:
    ops: tuple[dict[str, JsonValue], ...] = (
        {"op": "add", "path": "/elements/a", "value": {"type": "rectangle"}},
        {"op": "replace", "path": "/elements/a", "value": {"type": "rectangle", "x": 1}},
        {"op": "replace", "path": "x/elements/b", "value": {}},
        {"op": "replace", "path": "/elements/", "value": {}},
        {"op": "replace", "value": {}},
    )
    projected = _project(_patched(*ops))
    assert isinstance(projected, ElementsChanged)
    assert (projected.added, projected.changed, projected.removed) == (
        (),
        (ElementTouched(id="a"),),
        (),
    )


def test_a_commit_that_touches_no_element_bridges_nothing() -> None:
    image: dict[str, JsonValue] = {"sha256": "f" * 64, "size": 4, "media_type": "image/png"}
    assert _project(_patched({"op": "add", "path": "/files/" + "f" * 64, "value": image})) is None


def test_archiving_and_any_other_patch_are_bridged_as_by_default() -> None:
    archived = a.ArtifactArchived(artifact_id="d1", kind=Diagram.kind, version=5)
    assert isinstance(_project(archived), ArtifactArchived)
    edited = a.ArtifactChanged(
        artifact_id="d1",
        kind=Diagram.kind,
        version=2,
        patch=a.TextEdits(field="name", edits=(a.TextEdit(old="a", new="b"),)),
        summary="renamed",
    )
    assert _project(edited) is not None
    assert not isinstance(_project(edited), ElementsChanged)


async def _bridged(reader: r.Workspace, count: int, kind: str) -> None:
    seen = 0
    async with asyncio.timeout(30), aclosing(reader.subscribe()) as envelopes:
        async for got in envelopes:
            seen += got.event.event_type == kind
            if seen == count:
                return


async def test_a_rule_fires_once_a_commit_and_on_a_comment_finds_its_shape(
    ledger: Ledger,
) -> None:
    fired: list[reflexr.Event] = []

    async def record(reaction: r.Reaction[None]) -> None:
        fired.extend(each.event for each in reaction.events)

    rules = [
        reflexr.Rule(
            name="app:changed", when=reflexr.on(ElementsChanged), then=reflexr.run("record")
        ),
        reflexr.Rule(
            name="app:comments", when=reflexr.on(FeedbackGiven), then=reflexr.run("record")
        ),
    ]
    automation = r.Workspaces(
        r.InMemoryStorage(),
        events=[*BRIDGED, *EXCALIDRAW_EVENTS],
        publishers=EXCALIDRAW_PUBLISHERS,
        rules=rules,
    )

    async def on_open(tenant_id: str, workspace_id: str) -> None:
        await followers.watch(tenant_id, workspace_id)

    collaboration = artifactr.Workspaces(
        artifactr.InMemoryStorage(),
        types=EXCALIDRAW_TYPES,
        checks=excalidraw_checks(),
        on_open=on_open,
    )
    followers = Followers(
        collaboration, automation, ledger, projections=Projections(**EXCALIDRAW_PROJECTIONS)
    )
    reactor = r.Reactor(automation, actions={"record": record})
    try:
        ws = await collaboration.open(TENANT, WORKSPACE, actor=ALICE)
        first = Diagram(name="Plan", elements={"a": _element("a"), "b": _element("b")})
        await ws.commit(CreateArtifact(kind=Diagram.kind, artifact_id="d1", data=first.to_json()))
        moved = _element("a", 2, x=40)
        await ws.commit(
            EditArtifact(
                artifact_id="d1",
                base_version=1,
                patch=element_patch(first, {**first.elements, "a": moved}),
            )
        )
        await ws.commit(
            GiveFeedback(
                feedback_type=DiagramComment.feedback_type,
                target=ArtifactTarget(artifact_id="d1", version=2),
                value={"element_id": "b", "text": "make it bigger"},
            )
        )
        await ws.commit(ArchiveArtifact(artifact_id="d1", base_version=2))
        reader = await automation.open(TENANT, WORKSPACE, actor=reflexr.SystemActor())
        await _bridged(reader, 1, "artifactr:artifact_archived")
        await reactor.settle()
        # Restarted, on the same ledger: the log is followed again, and nothing fires twice.
        await followers.aclose()
        before = len(fired)
        followers = Followers(
            collaboration, automation, ledger, projections=Projections(**EXCALIDRAW_PROJECTIONS)
        )
        await followers.watch(TENANT, WORKSPACE)
        await ws.commit(
            GiveFeedback(
                feedback_type=DiagramComment.feedback_type,
                target=ArtifactTarget(artifact_id="d1", version=2),
                value={"element_id": "a", "text": "and this"},
            )
        )
        await _bridged(reader, 2, "artifactr:feedback_given")
        await reactor.settle()
        assert len(fired) == before + 1, "only the comment made after the restart"
    finally:
        await followers.aclose()

    changes = [event for event in fired if isinstance(event, ElementsChanged)]
    assert [(c.version, [e.id for e in c.added], [e.id for e in c.changed]) for c in changes] == [
        (1, ["a", "b"], []),
        (2, [], ["a"]),
    ]
    comment, after = [event for event in fired if isinstance(event, FeedbackGiven)]
    assert comment.value == {"element_id": "b", "text": "make it bigger"}
    assert after.value["element_id"] == "a"
    types = [each.event.event_type for each in await reader.read()]
    assert "artifactr:artifact_changed" not in types, "a diagram's commits became its own events"


async def test_no_client_publishes_a_diagrams_changes_itself() -> None:
    automation = r.Workspaces(
        r.InMemoryStorage(), events=EXCALIDRAW_EVENTS, publishers=EXCALIDRAW_PUBLISHERS
    )
    client = await automation.open(TENANT, WORKSPACE, actor=reflexr.UserActor(id="mallory"))
    forged = ElementsChanged(author=ALICE, diagram_id="d1", version=2)
    with pytest.raises(reflexr.core.Forbidden, match="reserved to source:artifactr"):
        await client.publish(forged)
    assert await client.as_actor(SOURCE).publish(forged), "the follower's publisher may"
