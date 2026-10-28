"""`create_native_file` live: each app the stackr template wires makes a blank file through its
real worker, the file opens, and the agent's first edit of it is proposed (lattice#874).

The apps are copier.yml's `crafts`, from which the template generates its `TYPES`, each with
the native type it keeps there. Each runs only where `ARTIFACTR_TEST_CRAFT` names it and
`ARTIFACTR_TEST_CRAFT_CLI` names its CLI, as `moon run artifactr:fidelity` sets them from
`scripts/craft APP cli`: Nightly's Fidelity job, once for each app. The worker is the one its
image runs, made from the environment as the image's is, called over HTTP in process.
"""

import os
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Final

import httpx
import pytest
import yaml
from pydantic_ai import Agent, ModelMessage, ModelRequest, ModelResponse, ToolReturnPart

import artifactr.files
from artifactr.agent import ArtifactWorkspace, Session
from artifactr.core import UserActor
from artifactr.files.app import AppCommand
from artifactr.files.blobs import InMemoryBlobs
from artifactr.files.checkouts import InMemoryCheckouts
from artifactr.files.craft import CRAFTS
from artifactr.files.manifest import NativeFile
from artifactr.files.native import NativeFiles
from artifactr.files.tools import native_file_tools
from artifactr.files.worker import Worker
from artifactr.files.worker.__main__ import worker_from_environment
from artifactr.workspace import InMemoryStorage, Workspaces
from tests.agent.conftest import Script, call, say
from tests.files.corpus.harness import pinned

COPIER: Final = Path(__file__).parents[4] / "stackr" / "copier.yml"
WIRED: Final[dict[str, type[NativeFile]]] = {
    app: getattr(artifactr.files, craft["type"])
    for app, craft in yaml.safe_load(COPIER.read_text())["crafts"]["default"].items()
}
"""Each app the template wires, and the native type it keeps, as copier.yml has them."""

FIRST: Final[dict[str, AppCommand]] = {
    app: AppCommand(name=name, args=args)
    for app, (name, args) in {
        "wordcraft": ("text.insert", {"text": "Day one"}),
        "gridcraft": ("cell.set", {"cell": "A1", "input": "Day one"}),
        "deckcraft": ("slide.new", {"title": "Day one"}),
        "pdfcraft": ("page.insert_blank", {"at": 2}),
        "cadcraft": ("line", {"points": [[0, 0], [100, 0]]}),
        "photocraft": ("layer.new.layer", {"name": "Day one"}),
        "vectorcraft": ("layer.new", {"name": "Day one"}),
        "designcraft": ("frame.create", {"rect": [36, 36, 300, 200], "text": "Day one"}),
        "figcraft": ("text.create", {"text": "Day one", "x": 0, "y": 0}),
        "filmcraft": ("file.newSequence", {"name": "Day one"}),
        "effectcraft": ("comp.new", {"name": "Day one", "duration": 2}),
        "soundcraft": ("track.new", {"kind": "instrument", "name": "Day one"}),
        "freecad": ("box", {"length": 10, "width": 10, "height": 10}),
        "blender": ("cube", {"size": 2}),
    }.items()
}
"""A first edit each app makes of its blank file, which changes it."""

ALICE = UserActor(id="alice", name="Alice")

NIGHTLY: Final = Path(__file__).parents[5] / ".github" / "workflows" / "nightly.yml"

# Each call to the app has NativeFiles' default deadline, 30 seconds: a create, an edit, a render.
pytestmark = pytest.mark.timeout(180)


def test_every_app_the_template_wires_has_a_first_edit() -> None:
    assert set(FIRST) == set(WIRED), "a new app needs its first edit here"


def test_nightly_runs_each_app_the_template_wires() -> None:
    jobs = yaml.safe_load(NIGHTLY.read_text())["jobs"]
    assert set(WIRED) <= set(jobs["fidelity"]["strategy"]["matrix"]["app"])


def _worker(app: str) -> Worker:
    """The app's worker, made from the environment as its image makes it, over its pinned CLI."""
    token = secrets.token_hex(32)
    served = worker_from_environment(
        {
            "WORKER_APP": app,
            "WORKER_CLI": os.environ["ARTIFACTR_TEST_CRAFT_CLI"],
            "WORKER_VERSION": pinned(app),
            "WORKER_TOKEN": token,
        }
    )
    return Worker.at("http://worker", token=token, transport=httpx.ASGITransport(app=served))


def _edit(app: str) -> Callable[[list[ModelMessage]], ModelResponse]:
    """The agent's next step: its first edit of the file the last call created, by its id."""

    def step(messages: list[ModelMessage]) -> ModelResponse:
        last = messages[-1]
        assert isinstance(last, ModelRequest)
        [returned] = [str(p.content) for p in last.parts if isinstance(p, ToolReturnPart)]
        created = returned.removeprefix("Created ").split(":")[0]
        return call(
            "edit_native",
            artifact_id=created,
            base_version=1,
            commands=[FIRST[app].model_dump(mode="json")],
            summary="Day one",
        )

    return step


@pytest.mark.parametrize("app", [pytest.param(a, marks=pytest.mark.craft(a)) for a in WIRED])
async def test_a_blank_file_is_created_opens_and_its_first_edit_is_proposed(app: str) -> None:
    file_type = WIRED[app]
    worker = _worker(app)
    await worker.open()
    try:
        assert (worker.name, worker.version) == (app, pinned(app))
        # As the template makes them: the app's deadline, its readings, its pace, the defaults.
        files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), {file_type: worker})
        ws = await Workspaces(InMemoryStorage(), types=[file_type]).open("acme", "w1", actor=ALICE)
        thread = await ws.create_thread("Trip")
        script = Script(
            call("create_native_file", type=file_type.kind, title="Trip"), _edit(app), say("Done.")
        )
        agent = Agent(
            script.model,
            deps_type=Session[None],
            toolsets=[native_file_tools(files)],
            capabilities=[ArtifactWorkspace(types=[file_type])],
        )
        deps = Session.start(ws, thread.id, app=None, run_id="run_1", on_behalf_of=ALICE)
        await agent.run("Write up the trip.", deps=deps)

        [created] = script.tool_returns(1)
        assert created.startswith("Created "), created
        [file] = await ws.artifacts(NativeFile)
        made = await ws.get(NativeFile, file.id)
        assert (file.kind, made.version, made.data.provenance.source) == (
            file_type.kind,
            1,
            "blank",
        )
        assert made.data.content.media_type in file_type.formats
        assert await files.read(ws, file.id), "the blank file's bytes"
        if made.data.text is not None:
            await files.read(ws, file.id, part="text")
        [edited] = script.tool_returns(2)
        assert edited.startswith("Proposed as "), edited
        assert (await ws.get(NativeFile, file.id)).version == 1, "the edit waits for review"
        # Its first page, as a person's preview asks for it, if the blank file has one.
        if CRAFTS[app].render and made.data.pages:
            png = await files.render(ws, file.id, 1)
            assert png.startswith(b"\x89PNG\r\n\x1a\n")
    finally:
        await worker.aclose()
