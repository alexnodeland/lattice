"""EffectCraft's adapter, against a stand-in for `effectcraft-cli mcp` that speaks its tools.

`fake_cli.py` is the stand-in, so these run on every pull request; `test_live.py` runs the same
calls against EffectCraft itself.
"""

import hashlib
import json
import stat
import sys
from pathlib import Path

import pytest

from artifactr.files.app import App, AppFailed
from artifactr.files.effectcraft import Subprocess
from artifactr.files.manifest import ECPROJ
from tests.files.corpus.made import step

FAKE = Path(__file__).with_name("fake_cli.py")
PNG = b"\x89PNG\r\n\x1a\n"

COMP = step("comp.new", name="Main", duration=2.5)


@pytest.fixture
def effectcraft(tmp_path: Path) -> Subprocess:
    cli = tmp_path / "effectcraft-cli"
    cli.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{FAKE}" "$@"\n')
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    return Subprocess(cli, version="0.11.1")


def test_it_is_an_app_that_people_check_out_and_in(effectcraft: Subprocess) -> None:
    app: App = effectcraft
    assert (app.name, app.version, app.build) == ("effectcraft", "0.11.1", None)
    assert (app.talk, app.integration) == ("save", "files:effectcraft")


async def test_a_batch_makes_a_project_and_says_what_is_in_it(effectcraft: Subprocess) -> None:
    applied = await effectcraft.apply(
        None,
        [
            step("project.newFolder", name="Parts"),
            step("comp.new", name="Inside", parent=1, duration=1),
            COMP,
            step("layer.newNull"),
            step("layer.newText", text="Hello"),
            step("comp.addMarker", time=0.5, comment="Beat"),
        ],
        deadline=20,
    )
    assert json.loads(applied.content)["savedBy"] == "0.11.1"
    inspection = applied.inspection
    assert inspection.fingerprint == hashlib.sha256(applied.content).hexdigest()
    assert inspection.outline == "\n".join(
        [
            "Parts (Folder)",
            "  Inside (Comp)",
            "Main (Comp)",
            "Composition Main:",
            "  Hello (Text)",
            "  Null (Null)",
        ]
    )
    assert inspection.text == "Hello"
    assert inspection.review == {"markers": [{"time": 0.5, "comment": "Beat"}]}
    assert (inspection.pages, inspection.media_type) == (3, ECPROJ)
    assert await effectcraft.inspect(applied.content, deadline=20) == inspection


async def test_an_item_numbered_as_its_own_folder_is_listed_once(
    effectcraft: Subprocess,
) -> None:
    project = json.loads((await effectcraft.apply(None, [COMP], deadline=20)).content)
    project["items"]["2"] = {"id": 1, "name": "Again", "kind": {"type": "Comp"}, "parent": 1}
    inspection = await effectcraft.inspect(json.dumps(project).encode(), deadline=20)
    assert inspection.outline.splitlines()[:2] == ["Main (Comp)", "Composition Main:"]


async def test_a_blank_project_has_no_composition_and_so_no_page(
    effectcraft: Subprocess,
) -> None:
    applied = await effectcraft.apply(None, [], deadline=20)
    inspection = applied.inspection
    assert (inspection.outline, inspection.text, inspection.pages) == ("", "", 0)
    assert inspection.review == {"markers": []}
    with pytest.raises(AppFailed, match="no page 1: the project's composition has 0") as refused:
        await effectcraft.render(applied.content, 1, scale=1, deadline=20)
    assert refused.value.failure == "refused"


async def test_a_page_is_a_second_of_the_composition(effectcraft: Subprocess) -> None:
    project = (await effectcraft.apply(None, [COMP], deadline=20)).content
    assert (await effectcraft.render(project, 3, scale=0.0001, deadline=20)).startswith(PNG)
    with pytest.raises(AppFailed, match="no page 4: the project's composition has 3"):
        await effectcraft.render(project, 4, scale=1, deadline=20)


async def test_a_batch_that_brings_in_footage_is_refused(effectcraft: Subprocess) -> None:
    importing = step("file.import", path="shot.mov")
    with pytest.raises(AppFailed, match=r"draws on what it doesn't hold: shot\.mov") as refused:
        await effectcraft.apply(None, [importing], deadline=20)
    assert refused.value.failure == "refused"


async def test_a_project_effectcraft_repairs_to_open_is_refused(effectcraft: Subprocess) -> None:
    project = json.loads((await effectcraft.apply(None, [], deadline=20)).content)
    repaired = {**project, "repaired": ["Main: frame rate 1000000000/1 fps to 1000/1 fps"]}
    with pytest.raises(AppFailed, match="repaired the project to open it") as refused:
        await effectcraft.inspect(json.dumps(repaired).encode(), deadline=20)
    assert refused.value.failure == "refused"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b'{"format": "aep"}', r"not a project its app saves as \.ecproj"),
        (b'{"savedBy": "0.11.1", "schema": 2, "items": []}', "its items aren't a project's"),
        (
            b'{"savedBy": "0.11.1", "schema": 2, "items": '
            b'{"1": {"name": "a.mov", "kind": {"type": "Footage", "path": "a.mov"}}}}',
            r"draws on what it doesn't hold: a\.mov",
        ),
    ],
)
async def test_a_file_that_isnt_a_whole_project_is_refused_before_it_is_opened(
    effectcraft: Subprocess, content: bytes, message: str
) -> None:
    with pytest.raises(AppFailed, match=message) as refused:
        await effectcraft.inspect(content, deadline=20)
    assert refused.value.failure == "refused"


async def test_a_command_that_fails_refuses_the_batch_and_is_named(
    effectcraft: Subprocess,
) -> None:
    with pytest.raises(AppFailed, match="nope: unknown command `nope`") as refused:
        await effectcraft.apply(None, [COMP, step("nope")], deadline=20)
    assert refused.value.failure == "refused"


async def test_it_finds_ten_commands_at_most(effectcraft: Subprocess) -> None:
    found = await effectcraft.commands("layer")
    assert len(found) == 6, "the stand-in repeats each match six times"
    assert (found[0].name, found[0].description) == ("layer.newText", "Text (Layer > New)")
