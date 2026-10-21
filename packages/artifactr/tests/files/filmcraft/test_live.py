"""FilmCraft itself, run headless from the pinned CLI: the adapter live.

These run only where `ARTIFACTR_TEST_CRAFT` is `filmcraft` and `ARTIFACTR_TEST_CRAFT_CLI` names
its CLI, as `moon run artifactr:fidelity` sets them from `scripts/craft filmcraft cli`. Its
fidelity report is the corpus harness's, `tests/files/corpus/test_fidelity.py`.
"""

import os

import pytest

from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.filmcraft import Subprocess
from artifactr.files.manifest import FCPROJ
from tests.files.corpus.filmcraft.corpus import CORPUS
from tests.files.corpus.filmcraft.make import MADE, SEQUENCE
from tests.files.corpus.harness import pinned
from tests.files.corpus.made import step

pytestmark = [pytest.mark.craft("filmcraft"), pytest.mark.timeout(120)]
DEADLINE = 20
VERSION = pinned("filmcraft")
"""The version scripts/craft pins, which the CLI must be."""


@pytest.fixture(scope="module")
def filmcraft() -> Subprocess:
    return Subprocess(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], version=VERSION, trusted=True)


async def test_commands_edit_and_the_outline_is_its_bins_and_clips(filmcraft: Subprocess) -> None:
    applied = await filmcraft.apply(
        None,
        [
            step("file.newBin", name="Selects"),
            SEQUENCE,
            step("graphics.newText", text="Hello", seconds=2),
            step("captions.newTrack", format="Subtitle"),
            step("captions.add", text="Spoken words", seconds=0, durationSeconds=1),
            step("markers.add", name="Beat", comment="Cut here", time=0),
        ],
        deadline=DEADLINE,
    )
    inspection = applied.inspection
    assert inspection.media_type == FCPROJ
    assert inspection.outline.splitlines() == [
        "Selects/",
        "Main (Sequence)",
        "Graphic (Graphic)",
        "Sequence Main:",
        "  Video 1: Hello",
    ]
    assert (inspection.text, inspection.pages) == ("Spoken words", 2)
    assert inspection.review == {"markers": [{"name": "Beat", "comment": "Cut here", "start": 0}]}
    png = await filmcraft.render(applied.content, 2, scale=0.25, deadline=DEADLINE)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    again = await filmcraft.apply(applied.content, [], deadline=DEADLINE)
    assert again.content == applied.content, "a save stamps nothing"


async def test_what_filmcraft_cant_do_is_refused(filmcraft: Subprocess) -> None:
    importing = AppCommand(name="file.import", args={"paths": ["/etc/hosts"]})
    for call in (
        filmcraft.apply(None, [AppCommand(name="format.disk")], deadline=DEADLINE),
        filmcraft.apply(None, [importing], deadline=DEADLINE),
        filmcraft.render(CORPUS.source("bins"), 1, scale=1, deadline=DEADLINE),
        filmcraft.render(CORPUS.source("clips"), 5, scale=1, deadline=DEADLINE),
    ):
        with pytest.raises(AppFailed) as refused:
            await call
        assert refused.value.failure == "refused"


async def test_it_finds_commands_in_its_catalog(filmcraft: Subprocess) -> None:
    found = await filmcraft.commands("razor")
    assert 0 < len(found) <= 10
    assert any(c.name == "timeline.razor" for c in found)


@pytest.mark.parametrize("feature", sorted(MADE.scripts))
async def test_each_corpus_file_is_what_filmcraft_makes_of_its_script(
    filmcraft: Subprocess, feature: str
) -> None:
    assert await MADE.make(filmcraft, feature) == MADE.committed(feature), "make it again"
