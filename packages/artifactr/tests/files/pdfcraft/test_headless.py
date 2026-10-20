"""PdfCraft's adapter, against a stand-in for `pdfcraft-cli mcp` that speaks its commands.

`fake_cli.py` is the stand-in, so these run on every pull request; `test_live.py` runs the same
calls against PdfCraft itself. What the `commands` dialect shares is held by its own tests.
"""

import stat
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from artifactr.files.app import App, AppCommand, AppFailed
from artifactr.files.pdfcraft import Subprocess, fingerprint

FAKE = Path(__file__).with_name("fake_cli.py")
PNG = b"\x89PNG\r\n\x1a\n"

Make = Callable[..., Subprocess]


@pytest.fixture
def spawn(tmp_path: Path) -> Make:
    """Make the adapter over the stand-in, misbehaving as `mode` says."""

    def spawn(mode: str = "") -> Subprocess:
        cli = tmp_path / f"pdfcraft-cli{mode}"
        cli.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{FAKE}" --mode "{mode}" "$@"\n')
        cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
        return Subprocess(cli, version="0.8.0", limit=1 << 20)

    return spawn


def command(command: str, **args: str | int) -> AppCommand:
    return AppCommand(name=command, args=dict(args))


def test_it_is_an_app_whose_build_is_bridged(spawn: Make) -> None:
    app: App = spawn()
    assert (app.name, app.version, app.build) == ("pdfcraft", "0.8.0", None)
    assert (app.talk, app.integration) == ("bridged", "files:pdfcraft")


async def test_a_batch_makes_a_document_and_says_what_is_in_it(spawn: Make) -> None:
    app = spawn()
    applied = await app.apply(
        None,
        [command("edit.add_text", page=1, text="Terms"), command("comment.add", text="Check")],
        deadline=20,
    )
    inspection = applied.inspection
    assert inspection.fingerprint == fingerprint(applied.content, limit=1 << 20)
    assert (inspection.outline, inspection.text) == ("Start\n  Detail", "Terms")
    assert inspection.review == {"comments": [{"page": 1, "contents": "Check"}]}
    assert (inspection.pages, inspection.media_type) == (1, "application/pdf")
    assert await app.inspect(applied.content, deadline=20) == inspection


async def test_a_blank_document_that_isnt_named_is_a_crash(spawn: Make) -> None:
    with pytest.raises(AppFailed, match="doc_create named no document as doc") as crashed:
        await spawn("nameless").apply(None, [], deadline=20)
    assert crashed.value.failure == "crashed"


async def test_a_document_pdfcraft_repaired_is_refused(spawn: Make) -> None:
    applied = await spawn().apply(None, [], deadline=20)
    with pytest.raises(AppFailed, match=r"not a whole \.pdf: rebuilt cross-reference") as refused:
        await spawn("repairing").inspect(applied.content, deadline=20)
    assert refused.value.failure == "refused"


async def test_a_command_that_fails_refuses_the_batch_and_is_named(spawn: Make) -> None:
    with pytest.raises(AppFailed, match="nope: command") as refused:
        await spawn().apply(None, [command("nope")], deadline=20)
    assert refused.value.failure == "refused"


async def test_it_renders_a_page_as_a_png(spawn: Make) -> None:
    app = spawn()
    applied = await app.apply(None, [], deadline=20)
    assert (await app.render(applied.content, 1, scale=0.5, deadline=20)).startswith(PNG)


async def test_it_finds_ten_commands_at_most(spawn: Make) -> None:
    found = await spawn().commands("edit")
    assert len(found) == 10
    assert (found[0].name, found[0].description) == ("edit.add_text", "Add text (Edit)")
