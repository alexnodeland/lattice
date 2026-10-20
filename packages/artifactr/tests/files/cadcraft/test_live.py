"""CADCraft itself, run headless from the pinned CLI: the adapter live.

These run only where `ARTIFACTR_TEST_CRAFT` is `cadcraft` and `ARTIFACTR_TEST_CRAFT_CLI` names
its CLI, as `moon run artifactr:fidelity` sets them from `scripts/craft cadcraft cli`. Its
fidelity report is the corpus harness's, `tests/files/corpus/test_fidelity.py`.
"""

import asyncio
import os

import pytest

from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.cadcraft import Subprocess
from artifactr.files.manifest import DWG, DXF
from tests.files.corpus.cadcraft.corpus import CORPUS
from tests.files.corpus.harness import pinned

pytestmark = [pytest.mark.craft("cadcraft"), pytest.mark.timeout(120)]
DEADLINE = 20
VERSION = pinned("cadcraft")
"""The version scripts/craft pins, which the CLI must be."""


@pytest.fixture(scope="module")
def cadcraft() -> Subprocess:
    return Subprocess(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], version=VERSION, trusted=True)


async def test_commands_draw_and_the_outline_is_what_was_drawn(cadcraft: Subprocess) -> None:
    applied = await cadcraft.apply(
        None,
        [
            AppCommand(name="layer.new", args={"name": "Walls", "current": True}),
            AppCommand(name="line", args={"points": [[0, 0], [100, 0]]}),
            AppCommand(name="text", args={"at": [5, 5], "text": "Kitchen"}),
        ],
        deadline=DEADLINE,
    )
    inspection = applied.inspection
    assert inspection.media_type == DXF
    assert "1 Line" in inspection.outline
    assert "Walls" in inspection.outline
    assert inspection.text == "Kitchen"
    png = await cadcraft.render(applied.content, 1, scale=0.25, deadline=DEADLINE)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


async def test_a_dwg_stays_a_dwg(
    cadcraft: Subprocess, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """CADCraft makes its own DWG sample; it is opened and saved as a DWG, never a DXF."""
    sample = tmp_path_factory.mktemp("dwg") / "bracket.dwg"
    process = await asyncio.create_subprocess_exec(
        os.environ["ARTIFACTR_TEST_CRAFT_CLI"], "sample", "bracket", str(sample)
    )
    assert await process.wait() == 0
    applied = await cadcraft.apply(sample.read_bytes(), [], deadline=DEADLINE)
    assert applied.content.startswith(b"AC10")
    assert applied.inspection.media_type == DWG
    again = await cadcraft.apply(applied.content, [], deadline=DEADLINE)
    assert again.content == applied.content, "a DWG saved twice is the same bytes"


async def test_what_cadcraft_cant_do_is_refused(cadcraft: Subprocess) -> None:
    for call in (
        cadcraft.apply(None, [AppCommand(name="format.disk")], deadline=DEADLINE),
        cadcraft.inspect(b"%PDF-1.7 not a drawing", deadline=DEADLINE),
        cadcraft.render(CORPUS.source("lines"), 2, scale=1, deadline=DEADLINE),
    ):
        with pytest.raises(AppFailed) as refused:
            await call
        assert refused.value.failure == "refused"


async def test_it_finds_commands_in_its_catalog(cadcraft: Subprocess) -> None:
    found = await cadcraft.commands("circle")
    assert 0 < len(found) <= 10
    assert any(c.name == "circle" for c in found)
