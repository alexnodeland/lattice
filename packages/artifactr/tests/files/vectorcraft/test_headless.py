"""VectorCraft's adapter, against a stand-in for `vectorcraft-cli mcp` that speaks its commands.

`fake_cli.py` is the stand-in, so these run on every pull request; `test_live.py` runs the same
calls against VectorCraft itself.
"""

import hashlib
import stat
import sys
from pathlib import Path

import pytest

from artifactr.files.app import App, AppCommand, AppFailed
from artifactr.files.manifest import SVG
from artifactr.files.vectorcraft import Subprocess

FAKE = Path(__file__).with_name("fake_cli.py")
PNG = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def vectorcraft(tmp_path: Path) -> Subprocess:
    cli = tmp_path / "vectorcraft-cli"
    cli.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{FAKE}" "$@"\n')
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    return Subprocess(cli, version="0.12.0")


def layer(name: str) -> AppCommand:
    return AppCommand(name="layer.new", args={"name": name})


def words(text: str) -> AppCommand:
    return AppCommand(name="type.add", args={"text": text})


def test_it_is_an_app_that_people_check_out_and_in(vectorcraft: Subprocess) -> None:
    app: App = vectorcraft
    assert (app.name, app.version, app.build) == ("vectorcraft", "0.12.0", None)
    assert (app.talk, app.integration) == ("save", "files:vectorcraft")


async def test_a_batch_makes_an_svg_and_says_what_is_in_it(vectorcraft: Subprocess) -> None:
    applied = await vectorcraft.apply(
        None, [layer("Plan"), words("Kitchen"), words("Hall")], deadline=20
    )
    assert applied.content.startswith(b"<svg")
    inspection = applied.inspection
    assert inspection.fingerprint == hashlib.sha256(applied.content).hexdigest()
    assert inspection.outline == "Plan\nLayer 1"
    assert (inspection.text, inspection.pages, inspection.media_type) == ("Hall\nKitchen", 1, SVG)
    assert await vectorcraft.inspect(applied.content, deadline=20) == inspection


async def test_bytes_that_arent_an_svg_are_refused_before_they_are_opened(
    vectorcraft: Subprocess,
) -> None:
    with pytest.raises(AppFailed, match="not an SVG") as refused:
        await vectorcraft.inspect(b"%PDF-1.7", deadline=20)
    assert refused.value.failure == "refused"


async def test_a_command_that_fails_refuses_the_batch_and_is_named(
    vectorcraft: Subprocess,
) -> None:
    with pytest.raises(AppFailed, match=r"nope: .*unknown command `nope`") as refused:
        await vectorcraft.apply(None, [layer("Plan"), AppCommand(name="nope")], deadline=20)
    assert refused.value.failure == "refused"


async def test_it_renders_each_artboard_as_a_page(vectorcraft: Subprocess) -> None:
    drawing = (await vectorcraft.apply(None, [], deadline=20)).content
    assert (await vectorcraft.render(drawing, 1, scale=0.0001, deadline=20)).startswith(PNG)
    with pytest.raises(AppFailed, match="no artboard 1") as refused:
        await vectorcraft.render(drawing, 2, scale=1, deadline=20)
    assert refused.value.failure == "refused"


async def test_it_finds_ten_commands_at_most(vectorcraft: Subprocess) -> None:
    found = await vectorcraft.commands("layer")
    assert len(found) == 6, "the stand-in repeats each match six times"
    assert (found[0].signature, found[0].description) == ("layer.new {name}", "New Layer (Layer)")
