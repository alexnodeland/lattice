"""The agent's diagram tools, run by artifactr's Runner on a scripted model, on every storage."""

import base64
import hashlib
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, Literal

import pytest
from pydantic_ai import Agent, BinaryContent, RetryPromptPart, ToolReturnPart

from artifactr.agent import ArtifactWorkspace, Runner, Session
from artifactr.core import CreateArtifact, RespondToProposal, Thread
from artifactr.excalidraw import (
    EXCALIDRAW,
    EXCALIDRAW_TYPES,
    ConversionFailed,
    Converted,
    Diagram,
    FakeConverter,
    diagram_tools,
)
from artifactr.excalidraw.converter import ConvertedFile, Format, Skeleton
from artifactr.excalidraw.tools import PAGE
from artifactr.excalidraw.types import MAX_VERSION
from artifactr.files.blobs import InMemoryBlobs
from artifactr.workspace import Scope, Workspace, Workspaces
from tests.excalidraw.scenes import data, element
from tests.ui.model import Script, call, say
from tests.ui.people import ALICE
from tests.ui.toggles import Toggles

PNG = b"\x89PNG\r\n\x1a\nimage"


class On:
    """Integrations where diagrams are on, as an application turns them on."""

    async def is_enabled(self, tenant_id: str, workspace_id: str, key: str, /) -> bool:
        return True


class Pictured(FakeConverter):
    """A converter that draws a Gantt chart as one picture, as Excalidraw's does."""

    async def mermaid(self, source: str, *, deadline: float = 10.0) -> Converted:
        if not source.startswith("gantt"):
            return await super().mermaid(source, deadline=deadline)
        image = element("img1", type="image", fileId="given1", status="saved")
        picture = ConvertedFile(media_type="image/png", data=base64.b64encode(PNG).decode())
        return Converted(elements=[image], files={"given1": picture})


class Broken(FakeConverter):
    async def render(
        self, diagram: Diagram, files: Mapping[str, bytes], *, as_: Format, deadline: float = 10.0
    ) -> bytes:
        raise ConversionFailed("crashed", "the worker failed")

    async def skeletons(
        self, skeletons: Sequence[Skeleton], *, deadline: float = 10.0
    ) -> Converted:
        raise ConversionFailed("too_large", "too many")


@pytest.fixture
async def ws(workspaces: Workspaces) -> Workspace:
    return await workspaces.open("tenant_a", "ws_1", actor=ALICE)


@pytest.fixture
async def thread(ws: Workspace) -> Thread:
    return await ws.create_thread("Design")


@pytest.fixture
async def runners(_no_task_left: None) -> AsyncIterator[list[Runner[None]]]:
    """The runners a test makes, each let finish handing its threads over, then closed.

    A hand-over queries the storage; cancelled mid-query by `_no_task_left`, it would leave a
    SQL connection checked out. So the hand-overs end first, and the runners are closed before
    `_no_task_left` (which they request) and before the storage they use.
    """
    made: list[Runner[None]] = []
    yield made
    for runner in made:
        await runner.drain()
        await runner.aclose()


def _runner(runners: list[Runner[None]], script: Script, **options: Any) -> Runner[None]:
    tools = diagram_tools(
        options.pop("converter", FakeConverter()),
        integrations=options.pop("integrations", On()),
        **options,
    )
    agent = Agent(
        script.model,
        deps_type=Session[None],
        toolsets=[tools],
        capabilities=[ArtifactWorkspace(types=EXCALIDRAW_TYPES)],
    )
    runner = Runner(agent, app=None)
    runners.append(runner)
    return runner


DIAGRAM_TOOLS = {"draw", "draw_mermaid", "edit_elements", "read_diagram", "view_diagram"}


def _offered(script: Script) -> list[list[str]]:
    """The diagram tools offered at each request, beside artifactr's own."""
    return [[tool for tool in tools if tool in DIAGRAM_TOOLS] for tools in script.tools]


async def _run(runner: Runner[None], ws: Workspace, thread: Thread) -> None:
    # Each run in a thread of its own: a thread runs one turn at a time.
    thread = await ws.create_thread(f"{thread.title} {len(await ws.threads())}")
    sent = await runner.send(ws, thread.id, "Draw it")
    assert sent.run is not None
    await sent.run.wait()


async def _accepted(ws: Workspace) -> Diagram:
    """Accept the one pending proposal, and return the diagram it made or changed."""
    [proposal] = await ws.proposals(status="pending")
    await ws.commit(RespondToProposal(proposal_id=proposal.id, decision="accept"))
    [diagram] = await ws.artifacts(Diagram)
    return diagram.data


def _returned(script: Script, request: int) -> list[Any]:
    return [p.content for p in script.last_parts(request) if isinstance(p, ToolReturnPart)]


def _retried(script: Script, request: int) -> list[str]:
    return [str(p.content) for p in script.last_parts(request) if isinstance(p, RetryPromptPart)]


async def test_mermaid_is_drawn_as_a_new_diagram_the_agent_proposes(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    script = Script(
        call(
            "draw_mermaid",
            mermaid="flowchart LR\n  API -- reads --> DB",
            summary="the stack",
            name="Stack",
        ),
        say("Drawn."),
    )
    await _run(_runner(runners, script), ws, thread)
    [proposal] = await ws.proposals(status="pending")
    assert proposal.proposed_by.kind == "agent"
    diagram = await _accepted(ws)
    assert diagram.name == "Stack"
    assert 'API" --"reads"--> ' in diagram.render_for_agent()


async def test_a_drawing_into_a_diagram_goes_beside_what_it_holds(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    await ws.commit(
        CreateArtifact(
            kind="excalidraw_diagram", artifact_id="d1", data=data(element("r1", x=0, width=300))
        )
    )
    skeletons = [{"type": "rectangle", "id": "box", "x": 0, "y": 0, "label": "New"}]
    script = Script(call("draw", id="d1", skeletons=skeletons, summary="a box"), say("Done."))
    await _run(_runner(runners, script), ws, thread)
    diagram = await _accepted(ws)
    assert (diagram.elements["box"].model_extra or {})["x"] == 300 + 120
    assert "r1" in diagram.elements


async def test_reading_a_diagram_gives_its_description_version_and_elements_by_page(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    many = [element(f"e{i}", x=i) for i in range(PAGE + 3)]
    labelled = [
        element(
            "a1", type="arrow", startBinding={"elementId": "e0"}, endBinding={"elementId": "e1"}
        ),
        element("t1", type="text", text="flow", containerId="a1"),
        element("t2", type="text", text="free"),
        element("gone", isDeleted=True),
    ]
    await ws.commit(
        CreateArtifact(kind="excalidraw_diagram", artifact_id="d1", data=data(*labelled, *many))
    )
    script = Script(
        call("read_diagram", "c1", id="d1"),
        call("read_diagram", "c2", id="d1", page=1),
        say("Read."),
    )
    await _run(_runner(runners, script), ws, thread)
    [first] = _returned(script, 1)
    lines = first.split("\n")
    assert lines[0].startswith("The diagram's words")
    assert (
        f"Version 1. Elements 1 to {PAGE} of {PAGE + 6}; read page 1 for more, of the same version."
        in lines
    )
    listed = json.loads(lines[-1])
    assert listed[0] == {
        "id": "a1",
        "type": "arrow",
        "label": "flow",
        "x": 0,
        "y": 0,
        "width": 10,
        "height": 10,
        "start": "e0",
        "end": "e1",
    }
    assert {
        "id": "t2",
        "type": "text",
        "text": "free",
        "x": 0,
        "y": 0,
        "width": 10,
        "height": 10,
    } in listed
    [second] = _returned(script, 2)
    assert f"Elements {PAGE + 1} to {PAGE + 6} of {PAGE + 6}." in second


async def test_edits_by_id_move_restyle_relabel_connect_and_delete(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    start = data(
        element("a"),
        element("b"),
        element("la", type="text", text="A", containerId="a"),
        element("note", type="text", text="old"),
    )
    await ws.commit(CreateArtifact(kind="excalidraw_diagram", artifact_id="d1", data=start))
    ops = [
        {"op": "move", "id": "a", "x": 40, "y": 50},
        {"op": "resize", "id": "a", "width": 300, "height": 90},
        {"op": "restyle", "id": "b", "stroke_color": "#1e1e1e"},
        {"op": "relabel", "id": "a", "text": "API"},
        {"op": "relabel", "id": "b", "text": "DB"},
        {"op": "relabel", "id": "note", "text": "new"},
        {"op": "connect", "start": "a", "end": "b", "label": "reads"},
        {"op": "connect", "start": "b", "end": "a"},
        {"op": "delete", "id": "note"},
    ]
    script = Script(
        call("edit_elements", id="d1", base_version=1, ops=ops, summary="tidied"), say("Done.")
    )
    await _run(_runner(runners, script), ws, thread)
    diagram = await _accepted(ws)
    a = diagram.elements["a"]
    assert ((a.model_extra or {})["x"], a.version) == (40, 3)
    assert (diagram.elements["b"].model_extra or {})["strokeColor"] == "#1e1e1e"
    assert diagram.elements["note"].is_deleted
    said = diagram.render_for_agent()
    assert '- rectangle a "API"' in said
    assert '- rectangle b "DB"' in said
    assert 'a "API" --"reads"--> b "DB"' in said
    assert 'b "DB" --> a "API"' in said


async def test_a_label_deleted_with_its_shape_and_a_stale_or_unknown_edit_go_back_to_the_model(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    start = data(element("a"), element("la", type="text", text="A", containerId="a"))
    await ws.commit(CreateArtifact(kind="excalidraw_diagram", artifact_id="d1", data=start))
    script = Script(
        call(
            "edit_elements",
            "c1",
            id="d1",
            base_version=7,
            ops=[{"op": "delete", "id": "a"}],
            summary="x",
        ),
        call(
            "edit_elements",
            "c2",
            id="d1",
            base_version=1,
            ops=[{"op": "move", "id": "zz", "x": 1, "y": 1}],
            summary="x",
        ),
        call(
            "edit_elements",
            "c3",
            id="d1",
            base_version=1,
            ops=[{"op": "delete", "id": "a"}],
            summary="gone",
        ),
        say("Done."),
    )
    await _run(_runner(runners, script), ws, thread)
    assert "is at version 1, not 7" in _retried(script, 1)[0]
    assert "There is no element zz" in _retried(script, 2)[0]
    diagram = await _accepted(ws)
    assert diagram.elements["a"].is_deleted
    assert diagram.elements["la"].is_deleted


async def test_a_drawing_that_fails_or_has_no_name_or_clashes_goes_back_to_the_model(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    await ws.commit(
        CreateArtifact(kind="excalidraw_diagram", artifact_id="d1", data=data(element("box")))
    )
    script = Script(
        call("draw_mermaid", "c1", mermaid="pie title Pets", summary="pets", name="Pets"),
        call("draw_mermaid", "c2", mermaid="flowchart LR\n  A --> B", summary="ab"),
        call("draw", "c3", id="d1", skeletons=[{"type": "rectangle", "id": "box"}], summary="box"),
        say("Sorry."),
    )
    await _run(_runner(runners, script), ws, thread)
    assert "Not drawn (unsupported)" in _retried(script, 1)[0]
    assert "needs a `name`" in _retried(script, 2)[0]
    assert "already has elements ['box']" in _retried(script, 3)[0]
    broken = Script(
        call("draw", skeletons=[{"type": "rectangle"}], summary="s", name="S"), say(".")
    )
    await _run(_runner(runners, broken, converter=Broken()), ws, thread)
    assert "Not drawn (too_large): too many" in _retried(broken, 1)[0]


async def test_a_picture_is_kept_in_the_blob_store_by_its_digest(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    blobs = InMemoryBlobs()
    script = Script(
        call("draw_mermaid", mermaid="gantt\n  title Launch", summary="launch", name="Launch"),
        say("Drawn."),
    )
    await _run(_runner(runners, script, converter=Pictured(), blobs=blobs), ws, thread)
    diagram = await _accepted(ws)
    [(digest, file)] = diagram.files.items()
    assert (file.size, file.media_type) == (len(PNG), "image/png")
    assert (diagram.elements["img1"].model_extra or {})["fileId"] == digest


async def test_without_a_store_a_picture_goes_back_to_the_model(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    script = Script(
        call("draw_mermaid", mermaid="gantt\n  title Launch", summary="launch", name="Launch"),
        say("Sorry."),
    )
    await _run(_runner(runners, script, converter=Pictured()), ws, thread)
    assert "Images aren't kept here" in _retried(script, 1)[0]


@pytest.mark.parametrize(
    ("media_type", "data", "said"),
    [
        ("image/png", "not base64!", "isn't base64"),
        ("image/png", base64.b64encode(b"GIF89a").decode(), "PNG isn't one"),
        (
            "image/svg+xml",
            base64.b64encode(
                b'<svg xmlns="http://www.w3.org/2000/svg"><script>x()</script></svg>'
            ).decode(),
            "can't be shown",
        ),
    ],
)
async def test_a_picture_that_isnt_what_it_says_is_neither_kept_nor_retried(
    ws: Workspace,
    thread: Thread,
    runners: list[Runner[None]],
    media_type: Literal["image/png", "image/svg+xml"],
    data: str,
    said: str,
) -> None:
    class Garbled(FakeConverter):
        async def mermaid(self, source: str, *, deadline: float = 10.0) -> Converted:
            picture = ConvertedFile(media_type=media_type, data=data)
            return Converted(
                elements=[element("img1", type="image", fileId="g")], files={"g": picture}
            )

    blobs = InMemoryBlobs()
    script = Script(call("draw_mermaid", mermaid="x", summary="x", name="X"), say("Sorry."))
    await _run(_runner(runners, script, converter=Garbled(), blobs=blobs), ws, thread)
    [answer] = _returned(script, 1)
    assert said in answer
    assert "don't try again" in answer
    assert _retried(script, 1) == []
    assert await ws.proposals(status="pending") == []


async def test_a_drawing_whose_ids_clash_keeps_no_images(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    await ws.commit(
        CreateArtifact(kind="excalidraw_diagram", artifact_id="d1", data=data(element("img1")))
    )
    blobs = InMemoryBlobs()
    script = Script(call("draw_mermaid", mermaid="gantt\n  x", summary="g", id="d1"), say("Sorry."))
    await _run(_runner(runners, script, converter=Pictured(), blobs=blobs), ws, thread)
    assert "already has elements ['img1']" in _retried(script, 1)[0]
    scope = Scope(ws.tenant_id, ws.workspace_id)
    assert await blobs.get(scope, "d1", hashlib.sha256(PNG).hexdigest()) is None


async def test_view_gives_the_model_a_png_with_the_diagrams_images(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    blobs = InMemoryBlobs()
    script = Script(
        call("draw_mermaid", "c1", mermaid="gantt\n  x", summary="g", name="G"),
        say("Drawn."),
    )
    await _run(_runner(runners, script, converter=Pictured(), blobs=blobs), ws, thread)
    await _accepted(ws)
    [diagram] = await ws.artifacts(Diagram)
    viewing = Script(call("view_diagram", id=diagram.id), say("Seen."))
    await _run(_runner(runners, viewing, converter=Pictured(), blobs=blobs, view=True), ws, thread)
    [png] = _returned(viewing, 1)
    assert isinstance(png, BinaryContent)
    assert png.data.startswith(b"\x89PNG")
    assert b"(1 images)" in png.data


async def test_view_without_a_store_or_a_failing_render_says_so(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    await ws.commit(
        CreateArtifact(kind="excalidraw_diagram", artifact_id="d1", data=data(element("a")))
    )
    seen = Script(call("view_diagram", "c1", id="d1"), say("Seen."))
    await _run(_runner(runners, seen, view=True), ws, thread)
    [png] = _returned(seen, 1)
    assert isinstance(png, BinaryContent)
    assert b"(0 images)" in png.data
    failing = Script(call("view_diagram", "c1", id="d1"), say("No."))
    await _run(_runner(runners, failing, converter=Broken(), view=True), ws, thread)
    assert _retried(failing, 1) == []
    assert _returned(failing, 1) == [
        "The diagram can't be shown: the worker failed. The converter is failing;"
        " don't try again now."
    ]


async def test_the_tools_are_offered_only_while_diagrams_are_on(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    toggles = Toggles()
    toggles.off["ws_1"] = {EXCALIDRAW}
    script = Script(say("No tools."))
    await _run(_runner(runners, script, integrations=toggles, view=True), ws, thread)
    assert _offered(script) == [[]]
    on = Script(say("Tools."))
    await _run(_runner(runners, on, integrations=On(), view=True), ws, thread)
    assert _offered(on) == [sorted(DIAGRAM_TOOLS)]


async def test_by_default_diagrams_are_off_and_offer_nothing(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    script = Script(say("No tools."))
    tools = diagram_tools(FakeConverter())
    agent = Agent(
        script.model,
        deps_type=Session[None],
        toolsets=[tools],
        capabilities=[ArtifactWorkspace(types=EXCALIDRAW_TYPES)],
    )
    runner = Runner(agent, app=None)
    runners.append(runner)
    await _run(runner, ws, thread)
    assert _offered(script) == [[]]


async def test_a_drawing_past_a_diagrams_limits_goes_back_to_the_model(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    class Huge(FakeConverter):
        async def mermaid(self, source: str, *, deadline: float = 10.0) -> Converted:
            return Converted(elements=[element("t1", type="text", text="x" * (1024 * 1024))])

    script = Script(call("draw_mermaid", mermaid="x", summary="x", name="X"), say("Sorry."))
    await _run(_runner(runners, script, converter=Huge()), ws, thread)
    assert "Not drawn:" in _retried(script, 1)[0]


async def test_into_a_diagram_with_nothing_live_a_drawing_stays_where_it_was_drawn(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    gone = element("old", isDeleted=True)
    await ws.commit(CreateArtifact(kind="excalidraw_diagram", artifact_id="d1", data=data(gone)))
    script = Script(
        call("draw", id="d1", skeletons=[{"type": "rectangle", "id": "box", "x": 5}], summary="b"),
        say("Done."),
    )
    await _run(_runner(runners, script), ws, thread)
    diagram = await _accepted(ws)
    assert (diagram.elements["box"].model_extra or {})["x"] == 5


async def test_an_element_with_no_place_is_read_without_one_and_a_lost_image_isnt_shown(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    image = {"sha256": "a" * 64, "size": 3, "media_type": "image/png"}
    placeless = element("p", x=None, y=None)
    start = {**data(placeless, element("q")), "files": {"a" * 64: image}}
    await ws.commit(CreateArtifact(kind="excalidraw_diagram", artifact_id="d1", data=start))
    script = Script(
        call("read_diagram", "c1", id="d1"),
        call("view_diagram", "c2", id="d1"),
        call(
            "edit_elements",
            "c3",
            id="d1",
            base_version=1,
            ops=[{"op": "delete", "id": "q"}],
            summary="x",
        ),
        say("Done."),
    )
    await _run(_runner(runners, script, view=True, blobs=InMemoryBlobs()), ws, thread)
    listed = json.loads(_returned(script, 1)[0].split("\n")[-1])
    assert {"id": "p", "type": "rectangle", "width": 10, "height": 10} in listed
    [png] = _returned(script, 2)
    assert b"(0 images)" in png.data, "its bytes were collected: the render goes on without them"


async def test_a_page_past_the_last_a_long_label_and_an_unknown_diagram_are_said_so(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    long = element("t", type="text", text="w" * 500)
    await ws.commit(CreateArtifact(kind="excalidraw_diagram", artifact_id="d1", data=data(long)))
    script = Script(
        call("read_diagram", "c1", id="d1", page=5),
        call("read_diagram", "c2", id="d1"),
        call("read_diagram", "c3", id="nope"),
        say("Read."),
    )
    await _run(_runner(runners, script), ws, thread)
    assert "No elements on page 5: version 1 has 1." in _returned(script, 1)[0]
    listed = json.loads(_returned(script, 2)[0].split("\n")[-1])
    assert listed[0]["text"] == "w" * 200 + "…"
    assert "There is no diagram 'nope' here" in _retried(script, 3)[0]


async def test_a_new_diagram_with_no_name_spends_no_converters_time(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    class Counting(FakeConverter):
        calls = 0

        async def mermaid(self, source: str, *, deadline: float = 10.0) -> Converted:
            Counting.calls += 1
            return await super().mermaid(source, deadline=deadline)

    script = Script(call("draw_mermaid", mermaid="graph TD\n  A --> B", summary="ab"), say("."))
    await _run(_runner(runners, script, converter=Counting()), ws, thread)
    assert "needs a `name`" in _retried(script, 1)[0]
    assert Counting.calls == 0


async def test_an_edit_out_of_reach_an_empty_restyle_and_a_bad_colour_go_back_to_the_model(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    await ws.commit(
        CreateArtifact(kind="excalidraw_diagram", artifact_id="d1", data=data(element("a")))
    )
    refused = [
        {"op": "move", "id": "a", "x": float("nan"), "y": 0},
        {"op": "move", "id": "a", "x": 1e12, "y": 0},
        {"op": "restyle", "id": "a"},
        {"op": "restyle", "id": "a", "stroke_color": "url(x)"},
    ]
    for op in refused:
        script = Script(
            call("edit_elements", id="d1", base_version=1, ops=[op], summary="x"), say("Sorry.")
        )
        await _run(_runner(runners, script), ws, thread)
        assert _retried(script, 1), op
    assert (await ws.get(Diagram, "d1")).version == 1


async def test_an_element_whose_change_isnt_one_goes_back_to_the_model(
    ws: Workspace, thread: Thread, runners: list[Runner[None]]
) -> None:
    near = element("a", version=MAX_VERSION)
    await ws.commit(CreateArtifact(kind="excalidraw_diagram", artifact_id="d1", data=data(near)))
    script = Script(
        call(
            "edit_elements",
            id="d1",
            base_version=1,
            ops=[{"op": "move", "id": "a", "x": 1, "y": 1}],
            summary="x",
        ),
        say("Sorry."),
    )
    await _run(_runner(runners, script), ws, thread)
    assert "Not changed: element a" in _retried(script, 1)[0]


async def test_images_too_large_to_show_are_said_so(
    ws: Workspace, thread: Thread, runners: list[Runner[None]], monkeypatch: pytest.MonkeyPatch
) -> None:
    blobs = InMemoryBlobs()
    script = Script(call("draw_mermaid", mermaid="gantt\n  x", summary="g", name="G"), say("."))
    await _run(_runner(runners, script, converter=Pictured(), blobs=blobs), ws, thread)
    await _accepted(ws)
    [diagram] = await ws.artifacts(Diagram)
    monkeypatch.setattr("artifactr.excalidraw.tools.MAX_RENDERING", 3)
    viewing = Script(call("view_diagram", id=diagram.id), say("."))
    await _run(_runner(runners, viewing, converter=Pictured(), blobs=blobs, view=True), ws, thread)
    assert "too large to show" in _retried(viewing, 1)[0]
