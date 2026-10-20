"""PhotoCraft's adapter, against a stand-in for `photocraft-cli mcp` that speaks its tools.

`fake_cli.py` is the stand-in, so these run on every pull request; `test_live.py` runs the same
calls against PhotoCraft itself.
"""

import hashlib
import stat
import sys
from pathlib import Path

import pytest

from artifactr.files.app import App, AppCommand, AppFailed
from artifactr.files.manifest import PSD
from artifactr.files.photocraft import Subprocess

FAKE = Path(__file__).with_name("fake_cli.py")
PNG = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def photocraft(tmp_path: Path) -> Subprocess:
    cli = tmp_path / "photocraft-cli"
    cli.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{FAKE}" "$@"\n')
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    return Subprocess(cli, version="0.9.0")


def layer(name: str) -> AppCommand:
    return AppCommand(name="layer.new.layer", args={"name": name})


def test_it_is_an_app_that_people_check_out_and_in(photocraft: Subprocess) -> None:
    app: App = photocraft
    assert (app.name, app.version, app.build) == ("photocraft", "0.9.0", None)
    assert (app.talk, app.integration) == ("save", "files:photocraft")


async def test_a_batch_makes_a_psd_and_says_what_is_in_it(photocraft: Subprocess) -> None:
    applied = await photocraft.apply(
        None,
        [layer("Ink"), AppCommand(name="type.create", args={"text": "Hello"})],
        deadline=20,
    )
    assert applied.content.startswith(b"8BPS\x00\x01")
    inspection = applied.inspection
    assert inspection.fingerprint == hashlib.sha256(applied.content).hexdigest()
    assert inspection.outline == "Group\n  Hello\nInk\nBackground"
    assert (inspection.text, inspection.review) == ("Hello", {"notes": []})
    assert (inspection.pages, inspection.media_type) == (1, PSD)
    assert await photocraft.inspect(applied.content, deadline=20) == inspection


@pytest.mark.parametrize(
    ("content", "message"),
    [(b"8BPS\x00\x02rest", "not a .psd: a .psb"), (b"\x89PNG", "not a .psd: no PSD header")],
)
async def test_a_file_that_isnt_a_psd_is_refused_before_it_is_opened(
    photocraft: Subprocess, content: bytes, message: str
) -> None:
    with pytest.raises(AppFailed, match=message) as refused:
        await photocraft.inspect(content, deadline=20)
    assert refused.value.failure == "refused"


@pytest.mark.parametrize(
    ("failing", "message"),
    [("nope", "nope: unknown command `nope`"), ("crash", "the batch crashed")],
)
async def test_a_command_that_fails_refuses_the_batch_and_is_named(
    photocraft: Subprocess, failing: str, message: str
) -> None:
    with pytest.raises(AppFailed, match=message) as refused:
        await photocraft.apply(None, [layer("Ink"), AppCommand(name=failing)], deadline=20)
    assert refused.value.failure == "refused"


async def test_it_renders_its_flattened_image_as_page_one(photocraft: Subprocess) -> None:
    image = (await photocraft.apply(None, [], deadline=20)).content
    assert (await photocraft.render(image, 1, scale=0.0001, deadline=20)).startswith(PNG)
    with pytest.raises(AppFailed, match="no page 2: PhotoCraft renders one") as refused:
        await photocraft.render(image, 2, scale=1, deadline=20)
    assert refused.value.failure == "refused"


async def test_it_finds_ten_commands_at_most(photocraft: Subprocess) -> None:
    found = await photocraft.commands("layer")
    assert len(found) == 10, "the stand-in repeats each match six times"
    assert (found[0].signature, found[0].description) == (
        "layer.new.layer {name}",
        "New Layer (Layer > New)",
    )
