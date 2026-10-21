"""FilmCraft's adapter, against a stand-in for `filmcraft-cli mcp` that speaks its tools.

`fake_cli.py` is the stand-in, so these run on every pull request; `test_live.py` runs the same
calls against FilmCraft itself.
"""

import hashlib
import json
import stat
import sys
from pathlib import Path

import pytest

from artifactr.files.app import App, AppFailed
from artifactr.files.filmcraft import Subprocess
from artifactr.files.manifest import FCPROJ
from tests.files.corpus.made import step

FAKE = Path(__file__).with_name("fake_cli.py")
PNG = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def filmcraft(tmp_path: Path) -> Subprocess:
    cli = tmp_path / "filmcraft-cli"
    cli.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{FAKE}" "$@"\n')
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    return Subprocess(cli, version="0.8.0", trusted=True)


SEQUENCE = step("file.newSequence", name="Main")
TITLE = step("graphics.newText", text="Hello", seconds=2.5)


def test_it_is_an_app_that_people_check_out_and_in(filmcraft: Subprocess) -> None:
    app: App = filmcraft
    assert (app.name, app.version, app.build) == ("filmcraft", "0.8.0", None)
    assert (app.talk, app.integration) == ("save", "files:filmcraft")


def test_it_runs_only_on_trusted_files_as_its_cli_confines_nothing() -> None:
    with pytest.raises(ValueError, match="confines no file"):
        Subprocess("filmcraft-cli", version="0.8.0")


async def test_a_batch_makes_a_project_and_says_what_is_in_it(filmcraft: Subprocess) -> None:
    applied = await filmcraft.apply(
        None,
        [
            step("file.newBin", name="Selects"),
            SEQUENCE,
            TITLE,
            step("markers.add", name="Beat"),
            step("captions.add", text="Spoken"),
        ],
        deadline=20,
    )
    assert json.loads(applied.content)["format"] == "filmcraft.project"
    inspection = applied.inspection
    assert inspection.fingerprint == hashlib.sha256(applied.content).hexdigest()
    assert inspection.outline == "Selects/\nMain (Sequence)\nSequence Main:\n  Video 1: Hello"
    assert inspection.text == "Spoken"
    assert inspection.review == {"markers": [{"name": "Beat", "comment": "", "start": 0}]}
    assert (inspection.pages, inspection.media_type) == (3, FCPROJ)
    assert await filmcraft.inspect(applied.content, deadline=20) == inspection


async def test_a_blank_project_has_no_sequence_and_so_no_page(filmcraft: Subprocess) -> None:
    applied = await filmcraft.apply(None, [], deadline=20)
    assert (applied.inspection.outline, applied.inspection.pages) == ("", 0)
    assert applied.inspection.review == {"markers": []}
    with pytest.raises(AppFailed, match="no page 1: the project's sequence has 0") as refused:
        await filmcraft.render(applied.content, 1, scale=1, deadline=20)
    assert refused.value.failure == "refused"


async def test_a_page_is_a_second_of_the_sequence(filmcraft: Subprocess) -> None:
    project = (await filmcraft.apply(None, [SEQUENCE, TITLE], deadline=20)).content
    assert (await filmcraft.render(project, 3, scale=0.0001, deadline=20)).startswith(PNG)
    with pytest.raises(AppFailed, match="no page 4: the project's sequence has 3") as refused:
        await filmcraft.render(project, 4, scale=1, deadline=20)
    assert refused.value.failure == "refused"


async def test_an_empty_sequence_has_a_page(filmcraft: Subprocess) -> None:
    project = (await filmcraft.apply(None, [SEQUENCE], deadline=20)).content
    assert (await filmcraft.render(project, 1, scale=1, deadline=20)).startswith(PNG)


async def test_a_batch_that_brings_in_a_file_is_refused(filmcraft: Subprocess) -> None:
    importing = step("file.importMedia", name="clip.mov", path="/etc/hosts")
    with pytest.raises(AppFailed, match=r"draws on files outside it: clip\.mov") as refused:
        await filmcraft.apply(None, [step("file.newBin", name="In"), importing], deadline=20)
    assert refused.value.failure == "refused"


@pytest.mark.parametrize(
    ("said", "message"),
    [
        ({"migrated": True}, "an older release's project, which a save would migrate"),
        ({"missing": 2}, "the project misses 2 media files"),
    ],
)
async def test_a_project_filmcraft_would_change_on_opening_is_refused(
    filmcraft: Subprocess, said: dict[str, object], message: str
) -> None:
    project = json.loads((await filmcraft.apply(None, [], deadline=20)).content)
    with pytest.raises(AppFailed, match=message) as refused:
        await filmcraft.inspect(json.dumps({**project, **said}).encode(), deadline=20)
    assert refused.value.failure == "refused"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b'{"format": "fcpxml"}', "not a .fcproj: no FilmCraft project"),
        (b'{"format": "filmcraft.project", "project": {}}', "its items aren't a project's"),
        (
            b'{"format": "filmcraft.project", "project": {"items": {"1": {"name": "a.mov", '
            b'"kind": {"Media": {"media": {"File": {"path": "a.mov"}}}}}}}}',
            r"draws on files outside it: a\.mov",
        ),
    ],
)
async def test_a_file_that_isnt_a_whole_project_is_refused_before_it_is_opened(
    filmcraft: Subprocess, content: bytes, message: str
) -> None:
    with pytest.raises(AppFailed, match=message) as refused:
        await filmcraft.inspect(content, deadline=20)
    assert refused.value.failure == "refused"


async def test_a_command_that_fails_refuses_the_batch_and_is_named(filmcraft: Subprocess) -> None:
    with pytest.raises(AppFailed, match="nope: unknown command `nope`") as refused:
        await filmcraft.apply(None, [SEQUENCE, step("nope")], deadline=20)
    assert refused.value.failure == "refused"


async def test_it_finds_ten_commands_at_most(filmcraft: Subprocess) -> None:
    found = await filmcraft.commands("razor")
    assert len(found) == 6, "the stand-in repeats each match six times"
    assert (found[0].name, found[0].description) == ("timeline.razor", "Razor")
