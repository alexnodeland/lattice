"""The `script` dialect's runner, against a stand-in for a CLI that runs a script on a call.

`fake_script_cli.py` is the stand-in, so these run on every pull request; FreeCAD's adapter is
run against FreeCAD itself by its live tests.
"""

import os
import stat
import sys
import time
from dataclasses import replace
from pathlib import Path

import anyio
import pytest
from pydantic import JsonValue

from artifactr.files.app import AppFailed
from artifactr.files.craft import CRAFTS, Craft, Script

FAKE = Path(__file__).with_name("fake_script_cli.py")
SCRIPTED = replace(CRAFTS["freecad"], name="scripted", cli="scripted-cli")


@pytest.fixture
def cli(tmp_path: Path) -> Path:
    cli = tmp_path / "scripted-cli"
    cli.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{FAKE}" "$@"\n')
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    return cli


def script(cli: Path, *, craft: Craft = SCRIPTED, limit: int = 1 << 20) -> Script:
    return Script(
        craft,
        cli,
        Path("script.py"),
        version="1.0.0",
        arguments=("--safe-mode",),
        ending=("--",),
        trusted=True,
        limit=limit,
    )


async def test_a_call_runs_the_script_in_its_own_directory_with_nothing_of_this_environment(
    cli: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SECRET", "kept here")
    call: dict[str, JsonValue] = {"do": "echo"}
    ran = await script(cli).run(10, call, b"the source", ".txt")
    assert isinstance(ran.result, dict)
    environment = ran.result.pop("environment")
    assert ran.result == {
        "arguments": ["--safe-mode", "script.py", "--"],
        "home": True,
        "source": "the source",
    }
    assert isinstance(environment, list)
    assert {"HOME", "LANG", "PATH", "QT_QPA_PLATFORM"} <= set(environment)
    assert "SECRET" not in environment, "the shell adds its own, and nothing of ours"
    assert ran.files == {}
    blank = await script(cli).run(10, call, None, ".txt")
    assert isinstance(blank.result, dict)
    assert blank.result["source"] is None


async def test_the_files_it_writes_come_back_and_one_past_the_limit_is_too_large(
    cli: Path,
) -> None:
    wanted = {"saved.txt"}
    ran = await script(cli, limit=8).run(
        10, {"do": "write", "size": 8}, None, ".txt", wanted=wanted
    )
    assert ran.files == {"saved.txt": b"x" * 8}
    unread = await script(cli, limit=8).run(10, {"do": "write", "size": 9}, None, ".txt")
    assert unread.files == {}, "a file not wanted is never read, however large"
    with pytest.raises(AppFailed, match=r"saved\.txt is larger than 8 bytes") as failed:
        await script(cli, limit=8).run(10, {"do": "write", "size": 9}, None, ".txt", wanted=wanted)
    assert failed.value.failure == "too_large"


@pytest.mark.parametrize(
    ("do", "failure", "message"),
    [
        ("refuse", "refused", "no such command"),
        ("other", "refused", "scripted-cli is 0.9.0, not 1.0.0"),
        ("crash", "crashed", "scripted-cli wrote no result; it printed: it ended"),
    ],
)
async def test_what_the_script_says_and_what_it_doesnt_are_typed_failures(
    cli: Path, do: str, failure: str, message: str
) -> None:
    with pytest.raises(AppFailed, match=message) as failed:
        await script(cli).run(10, {"do": do}, None, ".txt")
    assert failed.value.failure == failure


async def test_a_script_past_its_deadline_is_killed_with_the_call(cli: Path) -> None:
    started = time.monotonic()
    with pytest.raises(AppFailed, match=r"took more than 0\.5s") as failed:
        await script(cli).run(0.5, {"do": "hang"}, None, ".txt")
    assert failed.value.failure == "timeout"
    assert time.monotonic() - started < 5


async def test_nothing_the_cli_leaves_in_its_group_outlives_the_call(cli: Path) -> None:
    ran = await script(cli).run(10, {"do": "linger"}, None, ".txt", wanted={"lingering"})
    lingering = int(ran.files["lingering"])
    deadline = time.monotonic() + 5
    while _alive(lingering):
        assert time.monotonic() < deadline, f"{lingering} outlived the call"
        await anyio.sleep(0.05)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def test_it_starts_under_the_launcher(cli: Path, tmp_path: Path) -> None:
    launcher = tmp_path / "launcher"
    launcher.write_text('#!/bin/sh\n"$@"\necho launched >"$HOME/out/launched"\n')
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
    launched = Script(
        SCRIPTED,
        cli,
        Path("s.py"),
        version="1.0.0",
        trusted=True,
        limit=1 << 20,
        launcher=(str(launcher),),
    )
    ran = await launched.run(10, {"do": "write", "size": 1}, None, ".txt", wanted={"launched"})
    assert ran.files["launched"] == b"launched\n"


def test_an_app_that_confines_nothing_needs_the_operators_word(cli: Path) -> None:
    with pytest.raises(ValueError, match="confines no file its script reads or writes"):
        Script(SCRIPTED, cli, Path("s.py"), version="1.0.0", limit=1)
    confined = replace(SCRIPTED, roots="single")
    assert Script(confined, cli, Path("s.py"), version="1.0.0", limit=1).version == "1.0.0"
