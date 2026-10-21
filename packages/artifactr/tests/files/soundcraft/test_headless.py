"""SoundCraft's adapter, against a stand-in for `soundcraft-cli mcp` that speaks its tools.

`fake_cli.py` is the stand-in, so these run on every pull request; `test_live.py` runs the same
calls against SoundCraft itself.
"""

import hashlib
import json
import stat
import sys
from pathlib import Path

import pytest

from artifactr.files.app import App, AppCommand, AppFailed
from artifactr.files.manifest import SCRAFT
from artifactr.files.soundcraft import Subprocess
from tests.files.corpus.made import step

FAKE = Path(__file__).with_name("fake_cli.py")
KEYS = step("track.new", kind="instrument", name="Keys", comments="Play it softly")


@pytest.fixture
def soundcraft(tmp_path: Path) -> Subprocess:
    cli = tmp_path / "soundcraft-cli"
    cli.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{FAKE}" "$@"\n')
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    return Subprocess(cli, version="0.8.0")


def test_it_is_an_app_that_people_check_out_and_in(soundcraft: Subprocess) -> None:
    app: App = soundcraft
    assert (app.name, app.version, app.build) == ("soundcraft", "0.8.0", None)
    assert (app.talk, app.integration) == ("save", "files:soundcraft")


async def test_a_batch_makes_a_session_and_says_what_is_in_it(soundcraft: Subprocess) -> None:
    applied = await soundcraft.apply(
        None,
        [
            KEYS,
            step("midi.new_clip", track=1),
            step("track.new", name="Room", kind="aux"),
            step("mix.new_bus", name="Verb"),
            step("markers.add", name="Verse", at=48_000),
        ],
        deadline=20,
    )
    assert json.loads(applied.content)["format_version"] == 1
    inspection = applied.inspection
    assert inspection.fingerprint == hashlib.sha256(applied.content).hexdigest()
    assert inspection.outline == "Keys (instrument): Clip\nRoom (aux)\nVerb (bus)"
    assert inspection.text == "Play it softly"
    assert inspection.review == {"markers": [{"name": "Verse", "start": 48_000}]}
    assert (inspection.pages, inspection.media_type) == (None, SCRAFT)
    assert await soundcraft.inspect(applied.content, deadline=20) == inspection


async def test_it_renders_no_page(soundcraft: Subprocess) -> None:
    session = (await soundcraft.apply(None, [], deadline=20)).content
    with pytest.raises(AppFailed, match="SoundCraft renders no page headless") as refused:
        await soundcraft.render(session, 1, scale=1, deadline=20)
    assert refused.value.failure == "refused"


async def test_a_batch_that_brings_in_audio_is_refused(soundcraft: Subprocess) -> None:
    importing = step("file.import_audio", path="take.wav")
    with pytest.raises(AppFailed, match="draws on what it doesn't hold: take") as refused:
        await soundcraft.apply(None, [importing], deadline=20)
    assert refused.value.failure == "refused"


@pytest.mark.parametrize(
    ("command", "message"),
    [
        (step("engine.vst3_plugins", rescan=True), "engine.vst3_plugins: SoundCraft's adapter"),
        (step("app.quit"), "app.quit: SoundCraft's adapter runs no such command"),
        (
            step("mix.insert", track=1, plugin="clap:com.example.reverb"),
            "clap:com.example.reverb: SoundCraft's adapter loads no other plugins",
        ),
        (
            step("track.new", kind="instrument", instrument="vst3:0123"),
            "vst3:0123: SoundCraft's adapter loads no other plugins",
        ),
    ],
)
async def test_a_batch_that_reaches_past_the_session_is_refused_before_it_runs(
    soundcraft: Subprocess, command: AppCommand, message: str
) -> None:
    with pytest.raises(AppFailed, match=message) as refused:
        await soundcraft.apply(None, [KEYS, command], deadline=20)
    assert refused.value.failure == "refused"


async def test_a_session_that_misses_media_is_refused(soundcraft: Subprocess) -> None:
    session = json.loads((await soundcraft.apply(None, [], deadline=20)).content)
    missing = json.dumps({**session, "missing": ["take.wav"]}).encode()
    with pytest.raises(AppFailed, match="the session misses media") as refused:
        await soundcraft.inspect(missing, deadline=20)
    assert refused.value.failure == "refused"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b'{"format_version": 1}', r"not a project its app saves as \.scraft"),
        (b'{"format_version": 1, "tracks": [], "videos": {}}', "its sources aren't a session's"),
        (
            b'{"format_version": 1, "tracks": [], "sources": [{"name": "take"}]}',
            "draws on what it doesn't hold: take",
        ),
    ],
)
async def test_a_file_that_isnt_a_whole_session_is_refused_before_it_is_opened(
    soundcraft: Subprocess, content: bytes, message: str
) -> None:
    with pytest.raises(AppFailed, match=message) as refused:
        await soundcraft.inspect(content, deadline=20)
    assert refused.value.failure == "refused"


async def test_a_command_that_fails_refuses_the_batch_and_is_named(
    soundcraft: Subprocess,
) -> None:
    with pytest.raises(AppFailed, match="nope: unknown command `nope`") as refused:
        await soundcraft.apply(None, [KEYS, step("nope")], deadline=20)
    assert refused.value.failure == "refused"


async def test_it_finds_ten_commands_at_most(soundcraft: Subprocess) -> None:
    found = await soundcraft.commands("track")
    assert len(found) == 6, "the stand-in repeats each match six times"
    assert (found[0].name, found[0].description) == ("track.new", "New... (Track)")
