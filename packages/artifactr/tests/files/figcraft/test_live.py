"""FigCraft itself, run headless from the pinned CLI: the adapter live.

These run only where `ARTIFACTR_TEST_CRAFT` is `figcraft` and `ARTIFACTR_TEST_CRAFT_CLI` names
its CLI, as `moon run artifactr:fidelity` sets them from `scripts/craft figcraft cli`. Its
fidelity report is the corpus harness's, `tests/files/corpus/test_fidelity.py`.
"""

import io
import os
import zipfile

import pytest

from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.figcraft import Subprocess
from artifactr.files.manifest import FIGCRAFT
from tests.files.corpus.figcraft.corpus import CORPUS
from tests.files.corpus.harness import pinned

pytestmark = [pytest.mark.craft("figcraft"), pytest.mark.timeout(120)]
DEADLINE = 20
VERSION = pinned("figcraft")
"""The version scripts/craft pins, which the CLI must be."""


@pytest.fixture(scope="module")
def figcraft() -> Subprocess:
    return Subprocess(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], version=VERSION, trusted=True)


async def test_commands_design_and_the_outline_is_its_layers(figcraft: Subprocess) -> None:
    applied = await figcraft.apply(
        None,
        [
            AppCommand(
                name="frame.create",
                args={"x": 0, "y": 0, "width": 200, "height": 100, "name": "Card"},
            ),
            AppCommand(name="text.create", args={"text": "Hello", "x": 5, "y": 5, "parent": 2}),
            AppCommand(name="comment.add", args={"x": 1, "y": 1, "text": "Check", "author": "Ada"}),
        ],
        deadline=DEADLINE,
    )
    inspection = applied.inspection
    assert inspection.media_type == FIGCRAFT
    assert inspection.outline == "Page 1\n  Card\n    Hello"
    assert inspection.text == "Hello"
    comments = inspection.review["comments"]
    assert isinstance(comments, list)
    assert [c["text"] for c in comments if isinstance(c, dict)] == ["Check"]
    assert await figcraft.inspect(applied.content, deadline=DEADLINE) == inspection


async def test_what_figcraft_cant_do_is_refused(figcraft: Subprocess) -> None:
    for call in (
        figcraft.apply(None, [AppCommand(name="format.disk")], deadline=DEADLINE),
        figcraft.inspect(b'{"name": "a design as JSON"}', deadline=DEADLINE),
        figcraft.render(CORPUS.source("frames"), 9, scale=1, deadline=DEADLINE),
    ):
        with pytest.raises(AppFailed) as refused:
            await call
        assert refused.value.failure == "refused"


async def test_it_draws_a_canvas_page(figcraft: Subprocess) -> None:
    png = await figcraft.render(CORPUS.source("frames"), 1, scale=0.25, deadline=DEADLINE)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


async def test_a_blank_design_draws_its_page_as_its_background(figcraft: Subprocess) -> None:
    blank = (await figcraft.apply(None, [], deadline=DEADLINE)).content
    png = await figcraft.render(blank, 1, scale=0.25, deadline=DEADLINE)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert png[16:24] == bytes.fromhex("0000010000000100")


async def test_it_writes_its_format_first_as_the_adapter_reads_it(figcraft: Subprocess) -> None:
    """The adapter tells a `.figcraft` by its document's first key: a release that wrote it
    elsewhere would have every design refused, so this fails first."""
    saved = (await figcraft.apply(CORPUS.source("frames"), [], deadline=DEADLINE)).content
    with zipfile.ZipFile(io.BytesIO(saved)) as archive:
        assert archive.read("document.json").startswith(b'{"format":"figcraft"')


async def test_it_finds_commands_in_its_catalog(figcraft: Subprocess) -> None:
    found = await figcraft.commands("comment")
    assert 0 < len(found) <= 10
    assert any(c.name == "comment.add" for c in found)
