"""FigCraft's adapter, against a stand-in for `figcraft-cli mcp` that speaks its tools.

`fake_cli.py` is the stand-in, so these run on every pull request; `test_live.py` runs the same
calls against FigCraft itself.
"""

import hashlib
import stat
import sys
from pathlib import Path

import pytest

from artifactr.files.app import App, AppCommand, AppFailed
from artifactr.files.figcraft import Subprocess
from artifactr.files.manifest import FIGCRAFT

FAKE = Path(__file__).with_name("fake_cli.py")
PNG = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def figcraft(tmp_path: Path) -> Subprocess:
    cli = tmp_path / "figcraft-cli"
    cli.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{FAKE}" "$@"\n')
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    return Subprocess(cli, version="0.6.0", trusted=True)


def text(words: str) -> AppCommand:
    return AppCommand(name="text.create", args={"text": words, "x": 0, "y": 0})


def test_it_is_an_app_that_people_check_out_and_in_and_confines_nothing(
    figcraft: Subprocess,
) -> None:
    app: App = figcraft
    assert (app.name, app.version, app.build) == ("figcraft", "0.6.0", None)
    assert (app.talk, app.integration) == ("save", "files:figcraft")
    with pytest.raises(ValueError, match="figcraft-cli confines no file"):
        Subprocess("figcraft-cli", version="0.6.0")


async def test_a_batch_on_the_untitled_design_says_what_is_in_it(figcraft: Subprocess) -> None:
    applied = await figcraft.apply(
        None,
        [text("Hello"), text("World"), AppCommand(name="comment.add", args={"text": "Why?"})],
        deadline=20,
    )
    inspection = applied.inspection
    assert inspection.fingerprint == hashlib.sha256(applied.content).hexdigest()
    assert inspection.outline == "Page 1\n  Frame\n    Hello\n    World"
    assert (inspection.text, inspection.pages, inspection.media_type) == (
        "Hello\nWorld",
        1,
        FIGCRAFT,
    )
    assert inspection.review == {"comments": [{"id": 1, "text": "Why?"}]}
    assert await figcraft.inspect(applied.content, deadline=20) == inspection


async def test_what_isnt_a_figcraft_is_refused_before_it_is_opened(figcraft: Subprocess) -> None:
    with pytest.raises(AppFailed, match=r"not a \.figcraft") as refused:
        await figcraft.inspect(b'{"name": "a .fig as JSON"}', deadline=20)
    assert refused.value.failure == "refused"


async def test_a_command_that_fails_refuses_the_batch_and_is_named(figcraft: Subprocess) -> None:
    with pytest.raises(AppFailed, match="unknown command `nope`") as refused:
        await figcraft.apply(None, [text("Hello"), AppCommand(name="nope")], deadline=20)
    assert refused.value.failure == "refused"


async def test_it_renders_each_canvas_page_and_refuses_an_empty_one(figcraft: Subprocess) -> None:
    design = (await figcraft.apply(None, [text("Hello")], deadline=20)).content
    assert (await figcraft.render(design, 1, scale=0.0001, deadline=20)).startswith(PNG)
    with pytest.raises(AppFailed, match="no such page") as refused:
        await figcraft.render(design, 2, scale=1, deadline=20)
    assert refused.value.failure == "refused"
    blank = (await figcraft.apply(None, [], deadline=20)).content
    with pytest.raises(AppFailed, match="nothing to render"):
        await figcraft.render(blank, 1, scale=1, deadline=20)


async def test_it_finds_ten_commands_at_most_from_its_lines(figcraft: Subprocess) -> None:
    found = await figcraft.commands("")
    assert len(found) == 10, "the stand-in repeats each line four times; one isn't a command"
    created, shown = found[0], found[1]
    assert (created.name, created.signature, created.description) == (
        "text.create",
        "text.create {text, x, y}",
        "Text",
    )
    assert (shown.signature, shown.description) == ("view.comments {on?}", "Comments (View)")
    assert await figcraft.commands("zzz") == []
