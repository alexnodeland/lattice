"""DesignCraft itself, run headless from the pinned CLI: the adapter live.

These run only where `ARTIFACTR_TEST_CRAFT` is `designcraft` and `ARTIFACTR_TEST_CRAFT_CLI` names
its CLI, as `moon run artifactr:fidelity` sets them from `scripts/craft designcraft cli`. Its
fidelity report is the corpus harness's, `tests/files/corpus/test_fidelity.py`.
"""

import os

import pytest

from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.designcraft import Subprocess
from artifactr.files.manifest import IDML
from tests.files.corpus.designcraft.corpus import CORPUS
from tests.files.corpus.harness import pinned

pytestmark = [pytest.mark.craft("designcraft"), pytest.mark.timeout(120)]
DEADLINE = 20
VERSION = pinned("designcraft")
"""The version scripts/craft pins, which the CLI must be."""


@pytest.fixture(scope="module")
def designcraft() -> Subprocess:
    return Subprocess(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], version=VERSION)


async def test_commands_lay_out_a_page_saved_as_idml(designcraft: Subprocess) -> None:
    applied = await designcraft.apply(
        None,
        [
            AppCommand(
                name="frame.create",
                args={"rect": [36, 36, 300, 200], "content": "text", "text": "Contract\nTerms"},
            )
        ],
        deadline=DEADLINE,
    )
    inspection = applied.inspection
    assert inspection.media_type == IDML
    assert applied.content.startswith(b"PK")
    assert (inspection.outline, inspection.text, inspection.pages) == (
        "Contract",
        "Contract\nTerms",
        1,
    )
    png = await designcraft.render(applied.content, 1, scale=0.25, deadline=DEADLINE)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    # A new layout is saved with the ids its session gave it, which opening it numbers again:
    # its second save is the fixpoint, so a blank layout makes one revision more.
    again = await designcraft.apply(applied.content, [], deadline=DEADLINE)
    third = await designcraft.apply(again.content, [], deadline=DEADLINE)
    assert again.content != applied.content
    assert third.content == again.content


async def test_what_designcraft_cant_do_is_refused(designcraft: Subprocess) -> None:
    for call in (
        designcraft.apply(None, [AppCommand(name="format.disk")], deadline=DEADLINE),
        designcraft.inspect(b'{"format": "designcraft"}', deadline=DEADLINE),
        designcraft.render(CORPUS.source("text"), 2, scale=1, deadline=DEADLINE),
    ):
        with pytest.raises(AppFailed) as refused:
            await call
        assert refused.value.failure == "refused"


async def test_it_finds_commands_in_its_catalog(designcraft: Subprocess) -> None:
    found = await designcraft.commands("frame")
    assert 0 < len(found) <= 10
    assert any(c.name == "frame.create" for c in found)
