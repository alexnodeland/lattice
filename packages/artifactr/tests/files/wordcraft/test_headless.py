"""The headless adapter, against a stand-in for `wordcraft-cli mcp` that speaks its tools.

`fake_cli.py` is the stand-in, so these run on every pull request; `test_live.py` runs the same
calls against WordCraft itself.
"""

import os
import stat
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

from artifactr.files.app import App, AppCommand, AppFailed
from artifactr.files.wordcraft import Subprocess, fingerprint

FAKE = Path(__file__).with_name("fake_cli.py")
PNG = b"\x89PNG\r\n\x1a\n"

Make = Callable[..., Subprocess]


@pytest.fixture
def spawn(tmp_path: Path) -> Make:
    """Make the adapter over the stand-in, misbehaving as `mode` says."""

    def spawn(mode: str = "", *, limit: int = 1 << 20) -> Subprocess:
        cli = tmp_path / f"wordcraft-cli{mode}"
        cli.write_text(
            f'#!/bin/sh\nexport FAKE_PIDS="{tmp_path / "pids"}"\n'
            f'exec "{sys.executable}" -I "{FAKE}" --mode "{mode}" "$@"\n'
        )
        cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
        return Subprocess(cli, version="0.11.0", limit=limit)

    return spawn


def command(name: str, **args: str) -> AppCommand:
    return AppCommand(name=name, args=dict(args))


def test_it_is_an_app_that_people_check_out_and_in(spawn: Make) -> None:
    app: App = spawn()
    assert (app.name, app.version, app.build) == ("wordcraft", "0.11.0", None)
    assert (app.talk, app.integration) == ("bridged", "files:wordcraft")


async def test_a_command_past_the_open_file_is_refused_and_never_found(spawn: Make) -> None:
    app = spawn()
    with pytest.raises(AppFailed, match=r"file\.saveAs: WordCraft's adapter runs no such command"):
        await app.apply(None, [command("file.saveAs", path="/etc/x")], deadline=20)
    assert not [c for c in await app.commands("") if c.name.startswith("file.")]
    assert not await app.commands("save as")


async def test_a_batch_makes_a_file_and_says_what_is_in_it(spawn: Make) -> None:
    app = spawn()
    applied = await app.apply(
        None,
        [
            command("text.insert", text="Terms"),
            command("para.heading1"),
            command("text.insert", text="Pay within thirty days"),
            command("review.newComment", text="Check the dates"),
        ],
        deadline=20,
    )
    inspection = applied.inspection
    assert inspection.fingerprint == fingerprint(applied.content, limit=1 << 20)
    assert inspection.outline == "Terms", "the headings"
    assert inspection.text == "Terms\nPay within thirty days"
    assert inspection.review == {
        "comments": [{"id": 0, "text": "Check the dates"}],
        "changes": [],
    }
    assert inspection.pages == 2
    assert await app.inspect(applied.content, deadline=20) == inspection


async def test_every_save_stamps_the_bytes_and_not_the_fingerprint(spawn: Make) -> None:
    app = spawn()
    saved = await app.apply(None, [command("text.insert", text="One")], deadline=20)
    again = await app.apply(saved.content, [], deadline=20)
    assert saved.content != again.content
    assert saved.inspection == again.inspection


@pytest.mark.parametrize(
    ("mode", "message"), [("", "nope: unknown command"), ("garbled", "it failed")]
)
async def test_a_command_that_fails_refuses_the_batch_and_is_named(
    spawn: Make, mode: str, message: str
) -> None:
    with pytest.raises(AppFailed, match=message) as refused:
        await spawn(mode).apply(
            None, [command("text.insert", text="x"), command("nope")], deadline=20
        )
    assert refused.value.failure == "refused"


async def test_a_file_it_cant_open_is_refused(spawn: Make) -> None:
    with pytest.raises(AppFailed, match="not a valid zip package") as refused:
        await spawn().inspect(b"PK junk", deadline=20)
    assert refused.value.failure == "refused"


async def test_it_renders_a_page_as_a_png(spawn: Make) -> None:
    app = spawn()
    applied = await app.apply(None, [command("text.insert", text="One")], deadline=20)
    assert (await app.render(applied.content, 1, scale=0.5, deadline=20)).startswith(PNG)
    with pytest.raises(AppFailed, match="no page 2") as refused:
        await app.render(applied.content, 2, scale=1, deadline=20)
    assert refused.value.failure == "refused"


async def test_a_render_that_isnt_a_png_is_a_crash(spawn: Make) -> None:
    applied = await spawn().apply(None, [command("text.insert", text="One")], deadline=20)
    with pytest.raises(AppFailed, match="no PNG") as crashed:
        await spawn("textual").render(applied.content, 1, scale=1, deadline=20)
    assert crashed.value.failure == "crashed"


async def test_it_finds_ten_commands_at_most(spawn: Make) -> None:
    found = await spawn().commands("heading")
    assert len(found) == 5, "the stand-in repeats each match five times"
    assert found[0].name == "para.heading1"
    assert found[0].signature == "para.heading1 {}"
    assert found[0].description == "Heading 1 (Home > Styles)"
    assert len(await spawn().commands("")) == 10


async def test_a_cli_of_another_version_is_refused(spawn: Make) -> None:
    with pytest.raises(AppFailed, match=r"wordcraft-cli is 0\.0\.1, not 0\.11\.0") as refused:
        await spawn("version").apply(None, [], deadline=20)
    assert refused.value.failure == "refused"


async def test_a_call_past_its_deadline_times_out_and_ends_the_cli(
    spawn: Make, tmp_path: Path
) -> None:
    with pytest.raises(AppFailed, match="more than 2s") as late:
        await spawn("hang").apply(None, [], deadline=2)
    assert late.value.failure == "timeout"
    (pid,) = (tmp_path / "pids").read_text().split()
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid), 0)


async def test_a_cli_that_exits_mid_call_crashed_and_says_what_it_printed(spawn: Make) -> None:
    with pytest.raises(AppFailed, match=r"MCPError.*it printed: fake wordcraft-cli") as crashed:
        await spawn("exit").apply(None, [], deadline=20)
    assert crashed.value.failure == "crashed"


async def test_a_cli_that_cant_start_crashed(tmp_path: Path) -> None:
    with pytest.raises(AppFailed) as crashed:
        await Subprocess(tmp_path / "absent", version="0.11.0").inspect(b"", deadline=20)
    assert crashed.value.failure == "crashed"


async def test_a_saved_file_past_the_limit_is_too_large(spawn: Make) -> None:
    with pytest.raises(AppFailed, match="larger than 64 bytes") as large:
        await spawn(limit=64).apply(None, [command("text.insert", text="One")], deadline=20)
    assert large.value.failure == "too_large"


async def test_each_call_leaves_nothing_behind(
    spawn: Make, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    app = spawn()
    applied = await app.apply(None, [command("text.insert", text="One")], deadline=20)
    with pytest.raises(AppFailed):
        await app.render(applied.content, 9, scale=1, deadline=20)
    assert list(scratch.iterdir()) == []
