"""CADCraft's adapter, against a stand-in for `cadcraft-cli mcp` that speaks its tools.

`fake_cli.py` is the stand-in, so these run on every pull request; `test_live.py` runs the same
calls against CADCraft itself.
"""

import hashlib
import stat
import sys
from pathlib import Path

import pytest

from artifactr.files.app import App, AppCommand, AppFailed
from artifactr.files.cadcraft import Subprocess
from artifactr.files.manifest import DWG, DXF

FAKE = Path(__file__).with_name("fake_cli.py")
PNG = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def cadcraft(tmp_path: Path) -> Subprocess:
    cli = tmp_path / "cadcraft-cli"
    cli.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{FAKE}" "$@"\n')
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    return Subprocess(cli, version="0.8.0", trusted=True)


def line() -> AppCommand:
    return AppCommand(name="line", args={"points": [[0, 0], [1, 1]]})


def text(words: str) -> AppCommand:
    return AppCommand(name="text", args={"at": [0, 0], "text": words})


def test_it_is_an_app_bridged_to_its_build_and_confines_nothing(cadcraft: Subprocess) -> None:
    app: App = cadcraft
    assert (app.name, app.version, app.build) == ("cadcraft", "0.8.0", None)
    assert (app.talk, app.integration) == ("bridged", "files:cadcraft")
    with pytest.raises(ValueError, match="cadcraft-cli confines no file"):
        Subprocess("cadcraft-cli", version="0.8.0")


async def test_a_batch_makes_a_dxf_and_says_what_is_in_it(cadcraft: Subprocess) -> None:
    applied = await cadcraft.apply(None, [line(), text("Kitchen"), text("Hall")], deadline=20)
    assert applied.content.startswith(b"  0\nSECTION\n")
    inspection = applied.inspection
    assert inspection.fingerprint == hashlib.sha256(applied.content).hexdigest()
    assert inspection.outline == "Model: 1 Line, 2 Text\nLayers: 0, Walls\nLayouts: Layout1"
    assert (inspection.text, inspection.pages, inspection.media_type) == ("Kitchen\nHall", 1, DXF)
    assert await cadcraft.inspect(applied.content, deadline=20) == inspection


async def test_a_dwg_is_saved_as_a_dwg(cadcraft: Subprocess) -> None:
    applied = await cadcraft.apply(b'AC1032{"lines": 2, "texts": []}', [line()], deadline=20)
    assert applied.content.startswith(b"AC1032")
    assert applied.inspection.media_type == DWG
    assert applied.inspection.outline.startswith("Model: 3 Line\n")


async def test_bytes_that_arent_a_drawing_are_refused_before_they_are_opened(
    cadcraft: Subprocess,
) -> None:
    with pytest.raises(AppFailed, match="neither a DXF nor a DWG") as refused:
        await cadcraft.inspect(b"%PDF-1.7", deadline=20)
    assert refused.value.failure == "refused"


async def test_a_command_that_fails_refuses_the_batch_and_is_named(cadcraft: Subprocess) -> None:
    with pytest.raises(AppFailed, match=r"nope: .*unknown command `nope`") as refused:
        await cadcraft.apply(None, [line(), AppCommand(name="nope")], deadline=20)
    assert refused.value.failure == "refused"


async def test_it_renders_its_model_space_as_page_one(cadcraft: Subprocess) -> None:
    drawing = (await cadcraft.apply(None, [line()], deadline=20)).content
    assert (await cadcraft.render(drawing, 1, scale=0.001, deadline=20)).startswith(PNG)
    with pytest.raises(AppFailed, match="no page 2: CADCraft renders its model space") as refused:
        await cadcraft.render(drawing, 2, scale=1, deadline=20)
    assert refused.value.failure == "refused"


async def test_it_finds_ten_commands_at_most_by_their_menus(cadcraft: Subprocess) -> None:
    found = await cadcraft.commands("draw")
    assert len(found) == 10, "the stand-in repeats each match six times"
    assert (found[0].name, found[0].signature, found[0].description) == (
        "line",
        "line {points}",
        "Line (Draw > Line)",
    )
