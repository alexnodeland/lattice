"""DeckCraft's adapter, against a stand-in for `deckcraft-cli mcp` that speaks its tools.

`fake_cli.py` is the stand-in, so these run on every pull request; `test_live.py` runs the same
calls against DeckCraft itself. What every crafting app's CLI shares, its deadline, its version
and its crashes, is held by WordCraft's.
"""

import stat
import sys
from pathlib import Path

import pytest

from artifactr.files.app import App, AppCommand, AppFailed
from artifactr.files.deckcraft import Subprocess, fingerprint
from tests.files.corpus import package
from tests.files.corpus.deckcraft.corpus import CORPUS
from tests.files.corpus.gridcraft.corpus import CORPUS as XLSX

FAKE = Path(__file__).with_name("fake_cli.py")
PNG = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def deckcraft(tmp_path: Path) -> Subprocess:
    cli = tmp_path / "deckcraft-cli"
    cli.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{FAKE}" "$@"\n')
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    return Subprocess(cli, version="0.7.0", trusted=True, limit=1 << 20)


def command(command: str, **args: str) -> AppCommand:
    return AppCommand(name=command, args=dict(args))


def test_it_is_an_app_that_people_check_out_and_in(deckcraft: Subprocess) -> None:
    app: App = deckcraft
    assert (app.name, app.version, app.build) == ("deckcraft", "0.7.0", None)
    assert (app.talk, app.integration) == ("save", "files:deckcraft")


def test_its_cli_confines_nothing_so_it_runs_only_on_trusted_files() -> None:
    with pytest.raises(ValueError, match="confines no file"):
        Subprocess("deckcraft-cli", version="0.7.0")


async def test_a_batch_makes_a_deck_and_says_what_is_in_it(deckcraft: Subprocess) -> None:
    applied = await deckcraft.apply(
        None,
        [
            command("slide.new", title="Results"),
            command("text.add", text="Revenue grew."),
            command("comment.add", text="Check this"),
        ],
        deadline=20,
    )
    inspection = applied.inspection
    assert inspection.fingerprint == fingerprint(applied.content, limit=1 << 20)
    assert inspection.outline == "2. Results", "the first slide has no title"
    assert inspection.text == "\n\nResults\nRevenue grew.\na\tb\nc\td\nSay hello"
    assert inspection.review == {
        "comments": [{"slide": 2, "author": "Presenter", "text": "Check this"}]
    }
    assert inspection.pages == 2
    assert await deckcraft.inspect(applied.content, deadline=20) == inspection


async def test_a_command_that_fails_refuses_the_batch_and_is_named(deckcraft: Subprocess) -> None:
    with pytest.raises(AppFailed, match="nope: unknown command") as refused:
        await deckcraft.apply(None, [command("slide.new"), command("nope")], deadline=20)
    assert refused.value.failure == "refused"


@pytest.mark.parametrize(
    ("source", "found"),
    [
        (b"not a zip", "File is not a zip file"),
        (XLSX.source("values"), "it says it is no format"),
        (
            package.zipped({"mimetype": "application/vnd.oasis.opendocument.presentation"}),
            "it says it is application/vnd.oasis.opendocument.presentation",
        ),
    ],
    ids=["noise", "xlsx", "odp"],
)
async def test_a_file_of_another_format_is_refused_before_deckcraft_opens_it(
    deckcraft: Subprocess, source: bytes, found: str
) -> None:
    with pytest.raises(AppFailed, match=found) as refused:
        await deckcraft.apply(source, [], deadline=20)
    assert refused.value.failure == "refused"


async def test_a_deck_it_cant_open_is_refused(deckcraft: Subprocess) -> None:
    with pytest.raises(AppFailed, match="not a PPTX file") as refused:
        await deckcraft.inspect(CORPUS.source("text"), deadline=20)
    assert refused.value.failure == "refused"


async def test_it_renders_a_slide_numbered_from_one(deckcraft: Subprocess) -> None:
    applied = await deckcraft.apply(None, [], deadline=20)
    assert (await deckcraft.render(applied.content, 1, scale=0.5, deadline=20)).startswith(PNG)
    with pytest.raises(AppFailed, match="no slide 1") as refused:
        await deckcraft.render(applied.content, 2, scale=1, deadline=20)
    assert refused.value.failure == "refused"


async def test_it_finds_ten_commands_at_most_by_where_they_are(deckcraft: Subprocess) -> None:
    found = await deckcraft.commands("slide")
    assert len(found) == 6, "the stand-in repeats each match six times"
    assert (found[0].name, found[0].description) == ("slide.new", "New Slide (Home > Slides)")
    assert len(await deckcraft.commands("")) == 10
