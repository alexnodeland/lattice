"""VectorCraft itself, run headless from the pinned CLI: the adapter live.

These run only where `ARTIFACTR_TEST_CRAFT` is `vectorcraft` and `ARTIFACTR_TEST_CRAFT_CLI` names
its CLI, as `moon run artifactr:fidelity` sets them from `scripts/craft vectorcraft cli`. Its
fidelity report is the corpus harness's, `tests/files/corpus/test_fidelity.py`.
"""

import os

import pytest

from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.manifest import SVG
from artifactr.files.vectorcraft import Subprocess
from tests.files.corpus.harness import pinned
from tests.files.corpus.vectorcraft.corpus import CORPUS

pytestmark = [pytest.mark.craft("vectorcraft"), pytest.mark.timeout(120)]
DEADLINE = 20
VERSION = pinned("vectorcraft")
"""The version scripts/craft pins, which the CLI must be."""


@pytest.fixture(scope="module")
def vectorcraft() -> Subprocess:
    return Subprocess(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], version=VERSION)


async def test_commands_draw_and_the_outline_is_its_layers(vectorcraft: Subprocess) -> None:
    applied = await vectorcraft.apply(
        None,
        [
            AppCommand(name="layer.new", args={"name": "Plan"}),
            AppCommand(
                name="draw_shape",
                args={"shape": "rectangle", "x": 0, "y": 0, "width": 10, "height": 10},
            ),
        ],
        deadline=DEADLINE,
    )
    inspection = applied.inspection
    assert inspection.media_type == SVG
    assert inspection.outline.splitlines()[0] == "Plan"
    assert inspection.pages == 1
    png = await vectorcraft.render(applied.content, 1, scale=0.25, deadline=DEADLINE)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


async def test_an_svgs_layers_and_words_are_read(vectorcraft: Subprocess) -> None:
    groups = await vectorcraft.inspect(CORPUS.source("groups"), deadline=DEADLINE)
    assert groups.outline == "Front\n  house\nBack"
    text = await vectorcraft.inspect(CORPUS.source("text"), deadline=DEADLINE)
    assert text.text == "World\nHello", "top to bottom"


async def test_what_vectorcraft_cant_do_is_refused(vectorcraft: Subprocess) -> None:
    for call in (
        vectorcraft.apply(None, [AppCommand(name="format.disk")], deadline=DEADLINE),
        vectorcraft.inspect(b"%PDF-1.7 not an svg", deadline=DEADLINE),
        vectorcraft.render(CORPUS.source("shapes"), 2, scale=1, deadline=DEADLINE),
    ):
        with pytest.raises(AppFailed) as refused:
            await call
        assert refused.value.failure == "refused"


async def test_it_finds_commands_in_its_catalog(vectorcraft: Subprocess) -> None:
    found = await vectorcraft.commands("group")
    assert 0 < len(found) <= 10
    assert any(c.name == "object.group" for c in found)
