"""SoundCraft itself, run headless from the pinned CLI: the adapter live.

These run only where `ARTIFACTR_TEST_CRAFT` is `soundcraft` and `ARTIFACTR_TEST_CRAFT_CLI` names
its CLI, as `moon run artifactr:fidelity` sets them from `scripts/craft soundcraft cli`. Its
fidelity report is the corpus harness's, `tests/files/corpus/test_fidelity.py`.
"""

import os
from pathlib import Path

import pytest
from pydantic import JsonValue

from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.craft import CRAFTS, Server, Spawn
from artifactr.files.manifest import SCRAFT
from artifactr.files.soundcraft import Subprocess
from tests.files.corpus.harness import pinned
from tests.files.corpus.made import step
from tests.files.corpus.soundcraft.corpus import CORPUS
from tests.files.corpus.soundcraft.make import KEYS, MADE

pytestmark = [pytest.mark.craft("soundcraft"), pytest.mark.timeout(120)]
DEADLINE = 20
VERSION = pinned("soundcraft")
"""The version scripts/craft pins, which the CLI must be."""


@pytest.fixture(scope="module")
def soundcraft() -> Subprocess:
    return Subprocess(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], version=VERSION)


async def test_commands_compose_and_the_outline_is_its_tracks(soundcraft: Subprocess) -> None:
    applied = await soundcraft.apply(
        None,
        [
            KEYS,
            step("midi.new_clip", track=1, length=48_000),
            step("track.comments", track=1, comments="Play it softly"),
            step("mix.new_bus", name="Verb"),
            step("markers.add", name="Verse", at=48_000),
        ],
        deadline=DEADLINE,
    )
    inspection = applied.inspection
    assert inspection.media_type == SCRAFT
    assert inspection.outline.splitlines() == ["Keys (instrument): Keys", "Verb (bus)"]
    assert (inspection.text, inspection.pages) == ("Play it softly", None)
    assert inspection.review == {"markers": [{"name": "Verse", "start": 48_000}]}
    again = await soundcraft.apply(applied.content, [], deadline=DEADLINE)
    assert again.content == applied.content, "a save stamps nothing"


async def test_what_soundcraft_cant_do_is_refused(soundcraft: Subprocess) -> None:
    sampler = step("mix.sampler_load", track=1, path="/etc/hosts")
    for call in (
        soundcraft.apply(None, [AppCommand(name="format.disk")], deadline=DEADLINE),
        soundcraft.apply(None, [KEYS, sampler], deadline=DEADLINE),
        soundcraft.render(CORPUS.source("midi"), 1, scale=1, deadline=DEADLINE),
    ):
        with pytest.raises(AppFailed) as refused:
            await call
        assert refused.value.failure == "refused"


async def test_it_finds_commands_in_its_catalog(soundcraft: Subprocess) -> None:
    found = await soundcraft.commands("quantize")
    assert 0 < len(found) <= 10
    assert all("quantize" in f"{c.name} {c.description}".lower() for c in found)


async def test_a_file_outside_its_roots_is_refused(tmp_path: Path) -> None:
    """Its CLI is confined to the call's read and write roots: a session of its own, beside
    them, is refused unopened."""
    outside = tmp_path / "outside.scraft"
    outside.write_bytes(CORPUS.source("midi"))
    cli = os.environ["ARTIFACTR_TEST_CRAFT_CLI"]
    spawn = Spawn(CRAFTS["soundcraft"], cli, version=VERSION, limit=1 << 20)

    async def opening(server: Server) -> JsonValue:
        return await server.json("open_session", path=str(outside))

    with pytest.raises(AppFailed, match="automation") as refused:
        await spawn.run(DEADLINE, opening)
    assert refused.value.failure == "refused"


@pytest.mark.parametrize("feature", sorted(MADE.scripts))
async def test_each_corpus_file_is_what_soundcraft_makes_of_its_script(
    soundcraft: Subprocess, feature: str
) -> None:
    assert await MADE.make(soundcraft, feature) == MADE.committed(feature), "make it again"
