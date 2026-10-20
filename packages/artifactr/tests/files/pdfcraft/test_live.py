"""PdfCraft itself, run headless from the pinned CLI: the adapter live.

These run only where `ARTIFACTR_TEST_CRAFT` is `pdfcraft` and `ARTIFACTR_TEST_CRAFT_CLI` names
its CLI, as `moon run artifactr:fidelity` sets them from `scripts/craft pdfcraft cli`. Its
fidelity report is the corpus harness's, `tests/files/corpus/test_fidelity.py`.
"""

import asyncio
import os

import pytest

from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.pdfcraft import Subprocess
from tests.files.corpus.harness import pinned
from tests.files.corpus.pdfcraft.corpus import CORPUS

pytestmark = [pytest.mark.craft("pdfcraft"), pytest.mark.timeout(120)]
DEADLINE = 20
VERSION = pinned("pdfcraft")
"""The version scripts/craft pins, which the CLI must be."""


@pytest.fixture(scope="module")
def pdfcraft() -> Subprocess:
    return Subprocess(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], version=VERSION)


async def test_commands_edit_a_blank_document_and_it_renders(pdfcraft: Subprocess) -> None:
    applied = await pdfcraft.apply(
        None,
        [AppCommand(name="page.insert_blank", args={"at": 2})],
        deadline=DEADLINE,
    )
    assert (applied.inspection.pages, applied.inspection.media_type) == (2, "application/pdf")
    png = await pdfcraft.render(applied.content, 2, scale=0.25, deadline=DEADLINE)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


async def test_a_save_a_second_later_is_the_same_fingerprint(pdfcraft: Subprocess) -> None:
    once = await pdfcraft.apply(CORPUS.source("bookmarks"), [], deadline=DEADLINE)
    await asyncio.sleep(1.1)  # PdfCraft stamps each save's time, to the second
    twice = await pdfcraft.apply(once.content, [], deadline=DEADLINE)
    assert twice.content != once.content
    assert twice.inspection == once.inspection
    assert once.inspection.outline == "Introduction\nResults\n  By region"


async def test_what_pdfcraft_cant_do_is_refused(pdfcraft: Subprocess) -> None:
    for call in (
        pdfcraft.apply(None, [AppCommand(name="format.disk")], deadline=DEADLINE),
        pdfcraft.inspect(b"%PDF-1.7 and no more", deadline=DEADLINE),
        pdfcraft.render(CORPUS.source("text"), 9, scale=1, deadline=DEADLINE),
    ):
        with pytest.raises(AppFailed) as refused:
            await call
        assert refused.value.failure == "refused"


async def test_it_finds_commands_in_its_catalog(pdfcraft: Subprocess) -> None:
    found = await pdfcraft.commands("rotate")
    assert 0 < len(found) <= 10
    assert any(c.name.startswith("page.rotate") for c in found)
