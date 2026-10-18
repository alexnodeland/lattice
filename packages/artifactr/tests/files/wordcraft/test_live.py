"""WordCraft itself, run headless from the pinned CLI: the adapter live.

These run only where `ARTIFACTR_TEST_CRAFT` is `wordcraft` and `ARTIFACTR_TEST_CRAFT_CLI` names
its CLI, as `moon run artifactr:fidelity` sets them from `scripts/craft wordcraft cli`. Its
fidelity report is the corpus harness's, `tests/files/corpus/test_fidelity.py`.
"""

import os

import pytest

from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.wordcraft import Subprocess
from tests.files.corpus.harness import pinned
from tests.files.corpus.wordcraft.corpus import CORPUS

pytestmark = [pytest.mark.craft("wordcraft"), pytest.mark.timeout(120)]
DEADLINE = 20
VERSION = pinned("wordcraft")
"""The version scripts/craft pins, which the CLI must be."""


@pytest.fixture(scope="module")
def wordcraft() -> Subprocess:
    return Subprocess(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], version=VERSION)


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
        wordcraft.render(CORPUS.source("text"), 9, scale=1, deadline=DEADLINE),
    ):
        with pytest.raises(AppFailed) as refused:
            await call
        assert refused.value.failure == "refused"


async def test_it_finds_commands_in_its_catalog(wordcraft: Subprocess) -> None:
    found = await wordcraft.commands("comment")
    assert 0 < len(found) <= 10
    assert any(c.name == "review.newComment" for c in found)
