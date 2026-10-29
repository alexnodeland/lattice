"""Blender's adapter, against a stand-in for `blender` running its script.

`fake_cli.py` is the stand-in, so these run on every pull request; `test_live.py` runs the same
calls against Blender itself.
"""

import ast
import stat
import sys
import time
from pathlib import Path

import anyio
import pytest
from pydantic import JsonValue

from artifactr.files.app import App, AppCommand, AppFailed
from artifactr.files.blender import COMMANDS, Scanned, Subprocess, fingerprint, scan
from artifactr.files.blender.headless import EMPTY, SCANNING, SCRIPT, _scanned
from artifactr.files.craft import PREVIEW, Ran
from artifactr.files.manifest import BLEND
from tests.files.app.png import pixels
from tests.files.corpus.blender.corpus import CORPUS, HOSTILE, changed, inserted, plain

FAKE = Path(__file__).with_name("fake_cli.py")
PNG = b"\x89PNG\r\n\x1a\n"
SOURCE = CORPUS.source("primitives")


@pytest.fixture
def blender(tmp_path: Path) -> Subprocess:
    cli = tmp_path / "blender"
    cli.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{FAKE}" "$@"\n')
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    return Subprocess(cli, version="5.2.2", trusted=True)


def cube() -> AppCommand:
    return AppCommand(name="cube", args={"size": 1})


def test_it_is_an_app_that_talks_only_on_save_and_confines_nothing(blender: Subprocess) -> None:
    app: App = blender
    assert (app.name, app.version, app.build, app.talk) == ("blender", "5.2.2", None, "save")
    assert app.integration == "files:blender"
    with pytest.raises(ValueError, match="trusted=True"):
        Subprocess("blender", version="5.2.2")


async def test_a_batch_on_a_blank_file_saves_it_and_reads_it(blender: Subprocess) -> None:
    applied = await blender.apply(None, [cube(), cube()], deadline=10)
    assert applied.inspection.outline == (
        "Cube (MESH, in Scene Collection)\nCube0 (MESH, in Props)\nCube1 (MESH, in Props)"
    )
    assert applied.inspection.text == "Material: Red"
    assert (applied.inspection.pages, applied.inspection.media_type) == (1, BLEND)
    assert applied.inspection.fingerprint == fingerprint(applied.content)


async def test_blender_is_given_the_file_the_scan_wrote_and_twice_is_a_fixpoint(
    blender: Subprocess,
) -> None:
    once = await blender.apply(SOURCE, [], deadline=10)
    assert once.content == scan(SOURCE).content
    twice = await blender.apply(once.content, [], deadline=10)
    assert twice.inspection == once.inspection
    assert once.inspection.fingerprint == fingerprint(SOURCE), "only the thumbnail is gone"


async def test_a_file_keeps_whether_it_came_compressed(
    blender: Subprocess, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, JsonValue]] = []

    async def run(_: float, call: dict[str, JsonValue], *__: object, **___: object) -> Ran:
        calls.append(call)
        return Ran({}, {"document.blend": SOURCE})

    monkeypatch.setattr(blender._script, "run", run)
    for source in (None, SOURCE, bytes(plain("primitives"))):
        await blender.apply(source, [], deadline=10)
    assert [call["compressed"] for call in calls] == [True, True, False]


async def test_a_command_it_refuses_refuses_the_batch(blender: Subprocess) -> None:
    with pytest.raises(AppFailed, match="no command 'shell'") as failed:
        await blender.apply(None, [cube(), AppCommand(name="shell")], deadline=10)
    assert failed.value.failure == "refused"


async def test_a_file_holding_a_script_is_refused_before_blender_starts(
    blender: Subprocess,
) -> None:
    text = HOSTILE["text_block"]()
    for call in (
        blender.apply(text, [], deadline=10),
        blender.inspect(text, deadline=10),
        blender.render(text, 1, scale=1, deadline=10),
    ):
        with pytest.raises(AppFailed, match="a text, which may be a script"):
            await call


async def test_inspect_reads_the_source(blender: Subprocess) -> None:
    inspection = await blender.inspect(SOURCE, deadline=10)
    assert inspection.outline == "Cube (MESH, in Scene Collection)"
    assert inspection.fingerprint == fingerprint(SOURCE)


async def test_page_one_is_drawn_and_no_other(blender: Subprocess) -> None:
    assert await blender.render(SOURCE, 1, scale=0.5, deadline=10) == PNG
    with pytest.raises(AppFailed, match="no page 2"):
        await blender.render(SOURCE, 2, scale=1, deadline=10)


async def test_an_empty_scene_is_drawn_transparent_and_one_with_no_camera_refused(
    blender: Subprocess,
) -> None:
    empty = await blender.render(SOURCE, 1, scale=40 / PREVIEW, deadline=10)
    assert pixels(empty) == (40, 40, b"\x00" * 4)
    with pytest.raises(AppFailed, match="the scene has no camera") as refused:
        await blender.render(SOURCE, 1, scale=48 / PREVIEW, deadline=10)
    assert refused.value.failure == "refused"


def test_the_empty_scene_is_refused_in_the_scripts_own_words() -> None:
    assert f'Refused("{EMPTY}")' in SCRIPT.read_text()


async def test_a_save_or_a_page_it_doesnt_write_is_a_crash(blender: Subprocess) -> None:
    with pytest.raises(AppFailed, match="saved no file") as failed:
        await blender.apply(SOURCE, [AppCommand(name="unsaved")], deadline=10)
    assert failed.value.failure == "crashed"
    with pytest.raises(AppFailed, match="drew no page"):
        await blender.render(SOURCE, 1, scale=0.01, deadline=10)


async def test_its_commands_are_found_with_no_cli_started(blender: Subprocess) -> None:
    assert [c.name for c in await blender.commands("material")] == ["material", "assign"]
    assert len(await blender.commands("")) == 10


def test_its_commands_are_the_scripts() -> None:
    """The script runs in Blender alone, so its table is read from its source."""
    tree = ast.parse(SCRIPT.read_text())
    (table,) = [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "COMMANDS" for t in node.targets)
    ]
    assert isinstance(table, ast.Dict)
    assert [ast.literal_eval(key) for key in table.keys if key] == [c.name for c in COMMANDS]


async def test_a_batch_past_its_most_commands_or_a_scale_that_isnt_a_number_is_refused(
    blender: Subprocess,
) -> None:
    with pytest.raises(AppFailed, match="at most 200 commands"):
        await blender.apply(None, [cube()] * 201, deadline=10)
    for scale in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(AppFailed, match="a scale must be a positive number"):
            await blender.render(SOURCE, 1, scale=scale, deadline=10)


def slow() -> bytes:
    """A file of 400,000 node links, every pointer set: about a second of scanning, in budget."""
    return changed("materials", inserted("bNodeLink", b"\x11" * 56 * 400_000))


async def test_a_scan_past_the_deadline_stops_itself_and_none_overlaps_another(
    blender: Subprocess, monkeypatch: pytest.MonkeyPatch
) -> None:
    running, most = 0, 0

    def counted(source: bytes, limit: int, *, until: float) -> Scanned:
        nonlocal running, most
        running += 1
        most = max(most, running)
        try:
            return scan(source, limit, until=until)
        finally:
            running -= 1

    monkeypatch.setattr("artifactr.files.blender.headless.scan", counted)
    source = slow()
    started = time.monotonic()
    with pytest.raises(AppFailed, match="past its deadline") as failed:
        await blender.inspect(source, deadline=0.05)
    assert failed.value.failure == "timeout"
    assert time.monotonic() - started < 0.5, "the scan's thread stopped itself, and was waited for"

    failures: list[str] = []

    async def inspected() -> None:
        try:
            await blender.inspect(source, deadline=0.2)
        except AppFailed as error:
            failures.append(error.failure)

    async with anyio.create_task_group() as calls:
        for _ in range(3):
            calls.start_soon(inspected)
    assert failures == ["timeout"] * 3
    assert most == 1, "one scan at a time"


def test_a_scan_looks_at_its_deadline_while_it_inflates_and_reads_blocks() -> None:
    for content in (SOURCE, bytes(plain("primitives"))):
        with pytest.raises(AppFailed, match="past its deadline"):
            scan(content, until=time.monotonic() - 1)


def test_a_scan_that_cant_have_its_turn_in_time_is_a_timeout() -> None:
    """While another scan holds the lock past this one's deadline, this one is refused: whatever
    a busy machine does to the overlapping calls' timing above."""
    with SCANNING, pytest.raises(AppFailed, match="another scan ran past") as late:
        _scanned(CORPUS.source("primitives"), 1 << 30, until=time.monotonic())
    assert late.value.failure == "timeout"
