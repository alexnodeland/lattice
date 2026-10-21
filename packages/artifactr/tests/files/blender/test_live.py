"""Blender itself, run headless from the pinned `blender`: the adapter and its script live.

These run only where `ARTIFACTR_TEST_CRAFT` is `blender` and `ARTIFACTR_TEST_CRAFT_CLI` names
`blender`, as `moon run artifactr:fidelity` sets them from `scripts/craft blender cli`. Its
fidelity report is the corpus harness's, `tests/files/corpus/test_fidelity.py`. Between them,
every command and every step of `script.py` runs, which no pull request's coverage measures.
"""

import os
import subprocess
from pathlib import Path

import pytest

from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.blender import COMMANDS, Subprocess, scan
from artifactr.files.blender.headless import ARGUMENTS
from artifactr.files.manifest import BLEND
from tests.files.corpus.blender.corpus import CORPUS
from tests.files.corpus.harness import pinned

pytestmark = [pytest.mark.craft("blender"), pytest.mark.timeout(300)]
DEADLINE = 60
VERSION = pinned("blender")
"""The version scripts/craft pins, which the CLI must be."""


@pytest.fixture(scope="module")
def blender() -> Subprocess:
    return Subprocess(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], version=VERSION, trusted=True)


def command(called: str, /, **args: object) -> AppCommand:
    return AppCommand.model_validate({"name": called, "args": args})


EVERY = [
    command("cube", size=2, name="Block"),
    command("sphere", radius=1, at=[3, 0, 0]),
    command("cylinder", radius=0.5, depth=2, at=[0, 3, 0]),
    command("cone", radius1=1, radius2=0.2, depth=2, at=[3, 3, 0]),
    command("plane", size=10, at=[0, 0, -1]),
    command("move", object="Block", at=[0, 0, 1], rotation=[0, 0, 45], scale=[1, 1, 2]),
    command("material", name="Steel", color=[0.6, 0.6, 0.65], metallic=1, roughness=0.3),
    command("assign", object="Block", material="Steel"),
    command("modifier", object="Block", type="bevel", width=0.1, segments=3),
    command("modifier", object="Sphere", type="subdivision", levels=2),
    command("modifier", object="Cylinder", type="array", count=3),
    command("modifier", object="Cone", type="mirror", axes=[True, False, False]),
    command("modifier", object="Plane", type="solidify", thickness=0.1),
    command("camera", at=[8, -8, 6], lens=35),
    command("light", type="sun", energy=3, at=[0, 0, 10]),
    command("light", type="point", energy=500, at=[4, -2, 4], color=[1, 0.9, 0.8]),
    command("collection", name="Props"),
    command("collection", name="Small", parent="Props"),
    command("link", object="Sphere", collection="Small"),
    command("render", engine="cycles", width=640, height=360, samples=16),
    command("set", object="Cone", property="hide_render", value=True),
    command("set", object="Plane", property="name", value="Floor"),
    command("cube", size=1, name="Gone"),
    command("remove", object="Gone"),
]


async def test_every_command_builds_a_scene_that_saves_reads_scans_and_draws(
    blender: Subprocess,
) -> None:
    assert {c.name for c in COMMANDS} == {c.name for c in EVERY}
    applied = await blender.apply(None, EVERY, deadline=DEADLINE)
    inspection = applied.inspection
    assert inspection.media_type == BLEND
    assert "Sphere (MESH, in Small)" in inspection.outline
    assert "Floor (MESH, in Scene Collection)" in inspection.outline
    assert "Gone" not in inspection.outline
    assert inspection.text == "Material: Steel"
    assert scan(applied.content).compressed, "a blank file is saved as Blender's GUI saves one"
    png = await blender.render(applied.content, 1, scale=0.25, deadline=DEADLINE)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    again = await blender.apply(applied.content, [], deadline=DEADLINE)
    twice = await blender.apply(again.content, [], deadline=DEADLINE)
    assert twice.inspection == again.inspection, "a save of a saved scene changes nothing"


@pytest.mark.parametrize(
    ("commands", "why"),
    [
        ([command("python", code="import os")], "no command 'python'"),
        ([command("cube", size=-1)], "size must be from"),
        ([command("cube", size=1, shell=True)], "unknown argument shell"),
        ([command("modifier", object="Cube", type="nodes")], "type must be one of"),
        (
            [command("cube", size=1), command("set", object="Cube", property="data", value=1)],
            "property must be one of",
        ),
        ([command("assign", object="Nope", material="Nope")], "no object Nope"),
        ([command("light", type="laser", energy=1, at=[0, 0, 0])], "type must be one of"),
        ([command("render", engine="BLENDER_EEVEE_NEXT")], "engine must be one of"),
    ],
)
async def test_what_the_commands_dont_allow_is_refused(
    blender: Subprocess, commands: list[AppCommand], why: str
) -> None:
    with pytest.raises(AppFailed, match=why) as refused:
        await blender.apply(None, commands, deadline=DEADLINE)
    assert refused.value.failure == "refused"


async def test_a_scene_with_no_camera_has_nothing_to_draw_and_no_page_two(
    blender: Subprocess,
) -> None:
    for call in (
        blender.render(CORPUS.source("primitives"), 1, scale=1, deadline=DEADLINE),
        blender.render(CORPUS.source("camera_light"), 2, scale=1, deadline=DEADLINE),
    ):
        with pytest.raises(AppFailed) as refused:
            await call
        assert refused.value.failure == "refused"


@pytest.mark.parametrize("name", ["text_block", "python_driver"])
def test_blender_itself_runs_no_script_a_file_holds(tmp_path: Path, name: str) -> None:
    """The guard behind the scan, Blender's own: with scripts off, a file's text, registered to
    run on open, and a driver's Python, which leave a mark in `$HOME` if they run, don't."""
    path = tmp_path / f"{name}.blend"
    path.write_bytes(CORPUS.hostile_file(name))
    script = tmp_path / "open.py"
    script.write_text(
        "import bpy\n"
        f"bpy.ops.wm.open_mainfile(filepath={str(path)!r}, load_ui=False)\n"
        "bpy.context.view_layer.update()\n"
        "bpy.context.scene.frame_set(2)\n"
    )
    subprocess.run(
        [os.environ["ARTIFACTR_TEST_CRAFT_CLI"], *ARGUMENTS, str(script)],
        env={"HOME": str(tmp_path), "LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        timeout=120,
        check=True,
    )
    assert not (tmp_path / "ran").exists()
