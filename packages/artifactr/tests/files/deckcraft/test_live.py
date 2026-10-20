"""DeckCraft itself, run headless from the pinned CLI: the adapter live.

These run only where `ARTIFACTR_TEST_CRAFT` is `deckcraft` and `ARTIFACTR_TEST_CRAFT_CLI` names
its CLI, as `moon run artifactr:fidelity` sets them from `scripts/craft deckcraft cli`. Its
fidelity report is the corpus harness's, `tests/files/corpus/test_fidelity.py`.
"""

import os

import pytest

from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.deckcraft import Subprocess
from tests.files.corpus.deckcraft.corpus import CORPUS
from tests.files.corpus.harness import pinned

pytestmark = [pytest.mark.craft("deckcraft"), pytest.mark.timeout(120)]
DEADLINE = 20
VERSION = pinned("deckcraft")
"""The version scripts/craft pins, which the CLI must be."""


@pytest.fixture(scope="module")
def deckcraft() -> Subprocess:
    # These tests' files are made here: trusted, as DeckCraft's CLI confines nothing.
    return Subprocess(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], version=VERSION, trusted=True)


async def test_commands_edit_the_deck_and_the_outline_is_its_titles(deckcraft: Subprocess) -> None:
    applied = await deckcraft.apply(
        None,
        [
            AppCommand(name="slide.new", args={"layout": "titleAndContent"}),
            AppCommand(name="comment.add", args={"text": "Check the numbers"}),
        ],
        deadline=DEADLINE,
    )
    assert applied.inspection.pages == 2
    comments = applied.inspection.review["comments"]
    assert isinstance(comments, list)
    assert [(c["slide"], c["text"]) for c in comments if isinstance(c, dict)] == [
        (2, "Check the numbers")
    ]
    again = await deckcraft.apply(applied.content, [], deadline=DEADLINE)
    assert again.inspection == applied.inspection, "the same deck, however its XML is written"
    png = await deckcraft.render(CORPUS.source("text"), 1, scale=0.5, deadline=DEADLINE)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    inspection = await deckcraft.inspect(CORPUS.source("notes"), deadline=DEADLINE)
    assert (inspection.outline, inspection.text) == (
        "1. Agenda",
        "Agenda\nWelcome everyone, then the numbers.",
    )


async def test_what_deckcraft_cant_do_is_refused(deckcraft: Subprocess) -> None:
    for call in (
        deckcraft.apply(None, [AppCommand(name="format.disk")], deadline=DEADLINE),
        deckcraft.inspect(b"PK not a pptx", deadline=DEADLINE),
        deckcraft.render(CORPUS.source("text"), 9, scale=1, deadline=DEADLINE),
    ):
        with pytest.raises(AppFailed) as refused:
            await call
        assert refused.value.failure == "refused"


async def test_it_finds_commands_in_its_catalog(deckcraft: Subprocess) -> None:
    found = await deckcraft.commands("comment")
    assert 0 < len(found) <= 10
    assert any(c.name == "comment.add" and "(Review > Comments)" in c.description for c in found)
