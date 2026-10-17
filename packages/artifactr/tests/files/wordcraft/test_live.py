"""WordCraft itself, run headless from the pinned CLI: the fidelity report, and the adapter live.

These run only where `ARTIFACTR_TEST_WORDCRAFT` names a `wordcraft-cli`, as Nightly sets it from
`scripts/wordcraft cli`. Each corpus file is opened and saved, and its feature compared before and
after; saving it again must be a fixpoint. With `WORDCRAFT_MATRIX` set, the conftest writes the
results there as a Markdown matrix (lattice RFC-0003, phase 2).
"""

import os
import subprocess
import zipfile
from io import BytesIO

import pytest

from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.wordcraft import STAMPED, Subprocess
from tests.files.corpus.features import read
from tests.files.corpus.make import FEATURES, HERE

pytestmark = pytest.mark.wordcraft

DEADLINE = 30


@pytest.fixture(scope="module")
def wordcraft() -> Subprocess:
    cli = os.environ["ARTIFACTR_TEST_WORDCRAFT"]
    version = subprocess.run([cli, "--version"], check=True, capture_output=True, text=True)
    return Subprocess(cli, version=version.stdout.split()[-1])


def parts(content: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return {name: archive.read(name) for name in archive.namelist() if name not in STAMPED}


@pytest.mark.parametrize("feature", sorted(FEATURES))
async def test_an_open_and_a_save_keep_the_feature(wordcraft: Subprocess, feature: str) -> None:
    source = (HERE / f"{feature}.docx").read_bytes()
    saved = await wordcraft.apply(source, [], deadline=DEADLINE)
    assert read(feature, saved.content) == read(feature, source)


@pytest.mark.parametrize("feature", sorted(FEATURES))
async def test_saving_twice_is_a_fixpoint(wordcraft: Subprocess, feature: str) -> None:
    source = (HERE / f"{feature}.docx").read_bytes()
    once = await wordcraft.apply(source, [], deadline=DEADLINE)
    twice = await wordcraft.apply(once.content, [], deadline=DEADLINE)
    assert parts(twice.content) == parts(once.content)
    assert twice.inspection == once.inspection


async def test_commands_edit_the_file_and_the_outline_is_its_headings(
    wordcraft: Subprocess,
) -> None:
    def command(name: str, **args: str) -> AppCommand:
        return AppCommand(name=name, args=dict(args))

    applied = await wordcraft.apply(
        None,
        [
            command("para.heading1"),
            command("text.insert", text="Terms"),
            command("text.newParagraph"),
            command("para.normal"),
            command("text.insert", text="Pay within thirty days."),
            command("review.newComment", text="Check the dates"),
        ],
        deadline=DEADLINE,
    )
    inspection = applied.inspection
    assert inspection.outline == "Terms"
    assert "Pay within thirty days." in inspection.text
    comments = inspection.review["comments"]
    assert isinstance(comments, list)
    assert [c["text"] for c in comments if isinstance(c, dict)] == ["Check the dates"]
    assert inspection.pages == 1
    png = await wordcraft.render(applied.content, 1, scale=0.5, deadline=DEADLINE)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


async def test_what_wordcraft_cant_do_is_refused(wordcraft: Subprocess) -> None:
    for call in (
        wordcraft.apply(None, [AppCommand(name="format.disk")], deadline=DEADLINE),
        wordcraft.inspect(b"PK not a docx", deadline=DEADLINE),
        wordcraft.render((HERE / "text.docx").read_bytes(), 9, scale=1, deadline=DEADLINE),
    ):
        with pytest.raises(AppFailed) as refused:
            await call
        assert refused.value.failure == "refused"


async def test_it_finds_commands_in_its_catalog(wordcraft: Subprocess) -> None:
    found = await wordcraft.commands("comment")
    assert 0 < len(found) <= 10
    assert any(c.name == "review.newComment" for c in found)
