"""DesignCraft's adapter, against a stand-in for `designcraft-cli mcp` that speaks its tools.

`fake_cli.py` is the stand-in, so these run on every pull request; `test_live.py` runs the same
calls against DesignCraft itself.
"""

import hashlib
import stat
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from artifactr.files.app import App, AppCommand, AppFailed
from artifactr.files.designcraft import Subprocess
from artifactr.files.manifest import IDML

FAKE = Path(__file__).with_name("fake_cli.py")
PNG = b"\x89PNG\r\n\x1a\n"

Make = Callable[..., Subprocess]


@pytest.fixture
def spawn(tmp_path: Path) -> Make:
    """Make the adapter over the stand-in, misbehaving as `mode` says."""

    def spawn(mode: str = "") -> Subprocess:
        cli = tmp_path / f"designcraft-cli{mode}"
        cli.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{FAKE}" --mode "{mode}" "$@"\n')
        cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
        return Subprocess(cli, version="0.9.0")

    return spawn


def frame(words: str) -> AppCommand:
    return AppCommand(name="frame.create", args={"rect": [36, 36, 300, 200], "text": words})


def test_it_is_an_app_that_people_check_out_and_in(spawn: Make) -> None:
    app: App = spawn()
    assert (app.name, app.version, app.build) == ("designcraft", "0.9.0", None)
    assert (app.talk, app.integration) == ("save", "files:designcraft")


async def test_a_batch_makes_an_idml_package_and_says_what_is_in_it(spawn: Make) -> None:
    app = spawn()
    applied = await app.apply(None, [frame("Contract\nTerms"), frame("Fees")], deadline=20)
    inspection = applied.inspection
    assert inspection.fingerprint == hashlib.sha256(applied.content).hexdigest()
    assert inspection.outline == "Contract\nFees", "each story's first line"
    assert inspection.text == "Contract\nTerms\n\nFees"
    assert (inspection.pages, inspection.media_type) == (1, IDML)
    assert await app.inspect(applied.content, deadline=20) == inspection


async def test_what_isnt_an_idml_package_is_refused_before_it_is_opened(spawn: Make) -> None:
    for source in (b'{"format": "designcraft"}', b"\x06\x06\xed\xf5\xd8\x1dF\xe5 an INDD"):
        with pytest.raises(AppFailed, match="not an IDML package") as refused:
            await spawn().inspect(source, deadline=20)
        assert refused.value.failure == "refused"


@pytest.mark.parametrize(
    ("mode", "message"), [("", "nope: unknown command `nope`"), ("garbled", "it failed")]
)
async def test_a_command_that_fails_refuses_the_batch_and_is_named(
    spawn: Make, mode: str, message: str
) -> None:
    with pytest.raises(AppFailed, match=message) as refused:
        await spawn(mode).apply(None, [frame("One"), AppCommand(name="nope")], deadline=20)
    assert refused.value.failure == "refused"


async def test_it_renders_a_page_numbered_from_one(spawn: Make) -> None:
    app = spawn()
    layout = (await app.apply(None, [frame("One")], deadline=20)).content
    assert (await app.render(layout, 1, scale=0.5, deadline=20)).startswith(PNG)
    with pytest.raises(AppFailed, match="no page 1 ") as refused:
        await app.render(layout, 2, scale=1, deadline=20)
    assert refused.value.failure == "refused"


async def test_it_finds_ten_commands_at_most_by_their_menus(spawn: Make) -> None:
    found = await spawn().commands("frame")
    assert len(found) == 6, "the stand-in repeats each match six times"
    assert (found[0].name, found[0].signature, found[0].description) == (
        "frame.create",
        "frame.create {rect, text}",
        "Text Frame (Object)",
    )
