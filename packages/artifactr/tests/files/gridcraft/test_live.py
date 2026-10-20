"""GridCraft itself, run headless from the pinned CLI: the adapter live.

These run only where `ARTIFACTR_TEST_CRAFT` is `gridcraft` and `ARTIFACTR_TEST_CRAFT_CLI` names
its CLI, as `moon run artifactr:fidelity` sets them from `scripts/craft gridcraft cli`. Its
fidelity report is the corpus harness's, `tests/files/corpus/test_fidelity.py`.
"""

import os

import pytest

from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.gridcraft import Subprocess
from tests.files.corpus.gridcraft.corpus import CORPUS
from tests.files.corpus.harness import pinned

pytestmark = [pytest.mark.craft("gridcraft"), pytest.mark.timeout(120)]
DEADLINE = 20
VERSION = pinned("gridcraft")
"""The version scripts/craft pins, which the CLI must be."""


@pytest.fixture(scope="module")
def gridcraft() -> Subprocess:
    # These tests' files are made here: trusted, as GridCraft's CLI confines nothing.
    return Subprocess(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], version=VERSION, trusted=True)


async def test_commands_edit_the_workbook_and_its_text_is_its_cells(gridcraft: Subprocess) -> None:
    def command(name: str, **args: str) -> AppCommand:
        return AppCommand(name=name, args=dict(args))

    applied = await gridcraft.apply(
        None,
        [
            command("cell.set", cell="A1", input="Fee"),
            command("cell.set", cell="A2", input="100"),
            command("cell.set", cell="A3", input="=A2*2"),
        ],
        deadline=DEADLINE,
    )
    inspection = applied.inspection
    assert inspection.outline == "Sheet1 (A1:A3)"
    assert inspection.text == "Sheet1\nFee\n100\n200"
    again = await gridcraft.apply(applied.content, [], deadline=DEADLINE)
    assert again.content == applied.content, "GridCraft stamps nothing on a save"


async def test_what_gridcraft_cant_do_is_refused(gridcraft: Subprocess) -> None:
    for call in (
        gridcraft.apply(None, [AppCommand(name="format.disk")], deadline=DEADLINE),
        gridcraft.inspect(b"Item,Fee\nSetup,100\n", deadline=DEADLINE),
        gridcraft.render(CORPUS.source("values"), 1, scale=1, deadline=DEADLINE),
    ):
        with pytest.raises(AppFailed) as refused:
            await call
        assert refused.value.failure == "refused"


async def test_it_finds_commands_in_its_catalog(gridcraft: Subprocess) -> None:
    found = await gridcraft.commands("sort")
    assert 0 < len(found) <= 10
    assert any(c.name == "data.sort" and "(Data > Sort & Filter)" in c.description for c in found)
