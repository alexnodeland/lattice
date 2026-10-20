"""GridCraft's adapter, against a stand-in for `gridcraft-cli mcp` that speaks its tools.

`fake_cli.py` is the stand-in, so these run on every pull request; `test_live.py` runs the same
calls against GridCraft itself. What every crafting app's CLI shares, its deadline, its version
and its crashes, is held by WordCraft's.
"""

import stat
import sys
from pathlib import Path

import pytest

from artifactr.files.app import App, AppCommand, AppFailed
from artifactr.files.gridcraft import Subprocess, fingerprint
from tests.files.corpus import package
from tests.files.corpus.gridcraft.corpus import CORPUS
from tests.files.corpus.wordcraft.corpus import CORPUS as DOCX

FAKE = Path(__file__).with_name("fake_cli.py")


@pytest.fixture
def gridcraft(tmp_path: Path) -> Subprocess:
    cli = tmp_path / "gridcraft-cli"
    cli.write_text(
        f'#!/bin/sh\nexport FAKE_SAVES="{tmp_path / "saves"}"\n'
        f'exec "{sys.executable}" -I "{FAKE}" "$@"\n'
    )
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    return Subprocess(cli, version="0.8.0", trusted=True, limit=1 << 20)


def command(command: str, **args: str) -> AppCommand:
    return AppCommand(name=command, args=dict(args))


def test_it_is_an_app_whose_build_is_bridged(gridcraft: Subprocess) -> None:
    app: App = gridcraft
    assert (app.name, app.version, app.build) == ("gridcraft", "0.8.0", None)
    assert (app.talk, app.integration) == ("bridged", "files:gridcraft")


def test_its_cli_confines_nothing_so_it_runs_only_on_trusted_files() -> None:
    with pytest.raises(ValueError, match="confines no file"):
        Subprocess("gridcraft-cli", version="0.8.0")


async def test_a_batch_makes_a_workbook_and_says_what_is_in_it(gridcraft: Subprocess) -> None:
    applied = await gridcraft.apply(
        None,
        [command("cell.set", cell="A1", input="Fee"), command("sheet.add", name="Rates")],
        deadline=20,
    )
    inspection = applied.inspection
    assert inspection.fingerprint == fingerprint(applied.content, limit=1 << 20)
    assert inspection.outline == "Sheet1 (A1)\n  Fees\nRates"
    assert inspection.text == "Sheet1\nFee\t\n\nRates"
    assert (inspection.review, inspection.pages) == ({}, None)
    assert await gridcraft.inspect(applied.content, deadline=20) == inspection


async def test_a_command_that_fails_refuses_the_batch_and_is_named(
    gridcraft: Subprocess, tmp_path: Path
) -> None:
    with pytest.raises(AppFailed, match=r"nope: .*unknown command `nope`") as refused:
        await gridcraft.apply(
            None, [command("cell.set", cell="A1", input="1"), command("nope")], deadline=20
        )
    assert refused.value.failure == "refused"


@pytest.mark.parametrize(
    ("source", "found"),
    [
        (b"Item,Fee\nSetup,100\n", "File is not a zip file"),
        (DOCX.source("text"), "it says it is no format"),
        (
            package.zipped({"mimetype": "application/vnd.oasis.opendocument.spreadsheet"}),
            "it says it is application/vnd.oasis.opendocument.spreadsheet",
        ),
    ],
    ids=["csv", "docx", "ods"],
)
async def test_a_file_of_another_format_is_refused_before_gridcraft_opens_it(
    gridcraft: Subprocess, source: bytes, found: str
) -> None:
    with pytest.raises(AppFailed, match=found) as refused:
        await gridcraft.apply(source, [], deadline=20)
    assert refused.value.failure == "refused"


async def test_a_workbook_it_cant_open_is_refused(gridcraft: Subprocess) -> None:
    with pytest.raises(AppFailed, match="open_workbook") as refused:
        await gridcraft.inspect(CORPUS.source("values"), deadline=20)
    assert refused.value.failure == "refused"


async def test_it_renders_no_page(gridcraft: Subprocess) -> None:
    with pytest.raises(AppFailed, match="GridCraft renders no page headless") as refused:
        await gridcraft.render(CORPUS.source("values"), 1, scale=1, deadline=20)
    assert refused.value.failure == "refused"


async def test_it_finds_ten_commands_at_most_by_where_they_are(gridcraft: Subprocess) -> None:
    found = await gridcraft.commands("cell")
    assert len(found) == 6, "the stand-in repeats each match six times"
    assert (found[0].name, found[0].signature) == ("cell.set", "cell.set {cell, input}")
    assert found[0].description == "Enter (Home > Editing)"
    listed = await gridcraft.commands("")
    assert len(listed) == 10
    assert listed[1].description == "Insert Sheet", "in no menu"


async def test_a_batch_that_fails_after_a_command_ran_saves_nothing(
    gridcraft: Subprocess, tmp_path: Path
) -> None:
    source = (await gridcraft.apply(None, [], deadline=20)).content
    (tmp_path / "saves").unlink()
    with pytest.raises(AppFailed, match="nope"):
        await gridcraft.apply(
            source, [command("cell.set", cell="A1", input="1"), command("nope")], deadline=20
        )
    assert not (tmp_path / "saves").exists()


async def test_a_command_past_the_open_file_is_refused_and_never_found(
    gridcraft: Subprocess, tmp_path: Path
) -> None:
    with pytest.raises(AppFailed, match=r"file\.saveAs: GridCraft's adapter runs no such command"):
        await gridcraft.apply(None, [command("file.saveAs", path="/etc/x")], deadline=20)
    assert not (tmp_path / "saves").exists()
    assert not [c for c in await gridcraft.commands("") if c.name.startswith("file.")]


async def test_a_list_that_isnt_json_is_a_crash(gridcraft: Subprocess) -> None:
    with pytest.raises(AppFailed, match="list_commands replied with no JSON") as crashed:
        await gridcraft.commands("garbled")
    assert crashed.value.failure == "crashed"
