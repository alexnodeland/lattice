"""EffectCraft itself, run headless from the pinned CLI: the adapter live.

These run only where `ARTIFACTR_TEST_CRAFT` is `effectcraft` and `ARTIFACTR_TEST_CRAFT_CLI`
names its CLI, as `moon run artifactr:fidelity` sets them from `scripts/craft effectcraft cli`.
Its fidelity report is the corpus harness's, `tests/files/corpus/test_fidelity.py`.
"""

import os
from pathlib import Path

import pytest
from pydantic import JsonValue

from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.craft import CRAFTS, Server, Spawn
from artifactr.files.effectcraft import Subprocess
from artifactr.files.manifest import ECPROJ
from tests.files.corpus.effectcraft.corpus import CORPUS
from tests.files.corpus.effectcraft.make import COMP, MADE
from tests.files.corpus.harness import pinned
from tests.files.corpus.made import step

pytestmark = [pytest.mark.craft("effectcraft"), pytest.mark.timeout(120)]
DEADLINE = 20
VERSION = pinned("effectcraft")
"""The version scripts/craft pins, which the CLI must be."""


@pytest.fixture(scope="module")
def effectcraft() -> Subprocess:
    return Subprocess(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], version=VERSION)


async def test_commands_animate_and_the_outline_is_its_items_and_layers(
    effectcraft: Subprocess,
) -> None:
    applied = await effectcraft.apply(
        None,
        [
            step("project.newFolder", name="Parts"),
            COMP,
            step("layer.newText", text="Hello", size=12),
            step("layer.newShape", kind="ellipse", name="Dot"),
            step("comp.addMarker", time=0.5, comment="Beat"),
        ],
        deadline=DEADLINE,
    )
    inspection = applied.inspection
    assert inspection.media_type == ECPROJ
    assert inspection.outline.splitlines() == [
        "Parts (Folder)",
        "Main (Composition)",
        "Composition Main:",
        "  Dot (Shape)",
        "  Hello (Text)",
    ]
    assert (inspection.text, inspection.pages) == ("Hello", 2)
    assert inspection.review == {"markers": [{"time": 0.5, "comment": "Beat"}]}
    png = await effectcraft.render(applied.content, 2, scale=0.25, deadline=DEADLINE)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    again = await effectcraft.apply(applied.content, [], deadline=DEADLINE)
    assert again.content == applied.content, "a save stamps nothing"


async def test_what_effectcraft_cant_do_is_refused(effectcraft: Subprocess) -> None:
    script = AppCommand(name="script.run", args={"code": "app.project"})
    for call in (
        effectcraft.apply(None, [AppCommand(name="format.disk")], deadline=DEADLINE),
        effectcraft.apply(None, [script], deadline=DEADLINE),
        effectcraft.render(CORPUS.source("folders"), 3, scale=1, deadline=DEADLINE),
    ):
        with pytest.raises(AppFailed) as refused:
            await call
        assert refused.value.failure == "refused"


async def test_it_finds_commands_in_its_catalog(effectcraft: Subprocess) -> None:
    found = await effectcraft.commands("precompose")
    assert 0 < len(found) <= 10
    assert any(c.name == "layer.precompose" for c in found)


async def test_a_file_outside_its_roots_is_refused(tmp_path: Path) -> None:
    """Its CLI is confined to the call's read and write roots: a project of its own, beside
    them, is refused unopened."""
    outside = tmp_path / "outside.ecproj"
    outside.write_bytes(CORPUS.source("solids"))
    cli = os.environ["ARTIFACTR_TEST_CRAFT_CLI"]
    spawn = Spawn(CRAFTS["effectcraft"], cli, version=VERSION, limit=1 << 20)

    async def opening(server: Server) -> JsonValue:
        return await server.json("command_run", id="file.open", params={"path": str(outside)})

    with pytest.raises(AppFailed, match="outside the automation roots") as refused:
        await spawn.run(DEADLINE, opening)
    assert refused.value.failure == "refused"


@pytest.mark.parametrize("feature", sorted(MADE.scripts))
async def test_each_corpus_file_is_what_effectcraft_makes_of_its_script(
    effectcraft: Subprocess, feature: str
) -> None:
    assert await MADE.make(effectcraft, feature) == MADE.committed(feature), "make it again"
