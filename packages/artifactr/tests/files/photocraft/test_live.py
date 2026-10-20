"""PhotoCraft itself, run headless from the pinned CLI: the adapter live.

These run only where `ARTIFACTR_TEST_CRAFT` is `photocraft` and `ARTIFACTR_TEST_CRAFT_CLI` names
its CLI, as `moon run artifactr:fidelity` sets them from `scripts/craft photocraft cli`. Its
fidelity report is the corpus harness's, `tests/files/corpus/test_fidelity.py`.
"""

import os

import pytest

from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.manifest import PSD
from artifactr.files.photocraft import Subprocess
from tests.files.corpus.harness import pinned
from tests.files.corpus.photocraft.corpus import CORPUS

pytestmark = [pytest.mark.craft("photocraft"), pytest.mark.timeout(120)]
DEADLINE = 20
VERSION = pinned("photocraft")
"""The version scripts/craft pins, which the CLI must be."""


@pytest.fixture(scope="module")
def photocraft() -> Subprocess:
    return Subprocess(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], version=VERSION)


async def test_commands_add_layers_and_the_outline_is_its_layers(photocraft: Subprocess) -> None:
    applied = await photocraft.apply(
        None,
        [
            AppCommand(name="layer.new.layer", args={"name": "Ink"}),
            AppCommand(name="type.create", args={"text": "Hello", "x": 10, "y": 40}),
        ],
        deadline=DEADLINE,
    )
    inspection = applied.inspection
    assert applied.content.startswith(b"8BPS\x00\x01")
    assert inspection.media_type == PSD
    assert inspection.outline.splitlines()[1:] == ["Ink", "Background"]
    assert inspection.text == "Hello"
    png = await photocraft.render(applied.content, 1, scale=0.25, deadline=DEADLINE)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    again = await photocraft.apply(applied.content, [], deadline=DEADLINE)
    assert again.content == applied.content, "a save stamps nothing"


async def test_what_photocraft_cant_do_is_refused(photocraft: Subprocess) -> None:
    for call in (
        photocraft.apply(None, [AppCommand(name="format.disk")], deadline=DEADLINE),
        photocraft.inspect(b"8BPS\x00\x01 not a document", deadline=DEADLINE),
        photocraft.render(CORPUS.source("resolution"), 2, scale=1, deadline=DEADLINE),
    ):
        with pytest.raises(AppFailed) as refused:
            await call
        assert refused.value.failure == "refused"


async def test_it_finds_commands_in_its_catalog(photocraft: Subprocess) -> None:
    found = await photocraft.commands("gaussian")
    assert 0 < len(found) <= 10
    assert any(c.name == "filter.blur.gaussianBlur" for c in found)
