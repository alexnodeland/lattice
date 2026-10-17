"""The fake app: what tests of native files run against, behaving as an app does."""

import zlib

import pytest

from artifactr.files.app import App, AppCommand, AppFailed, Failure, FakeApp
from artifactr.files.app.fake import PAGE
from artifactr.files.manifest import OUTLINE_LIMIT


def command(name: str, **args: object) -> AppCommand:
    return AppCommand.model_validate({"name": name, "args": args})


def test_it_is_an_app() -> None:
    app: App = FakeApp()
    assert (app.name, app.version, app.build) == ("fake", "1.0", None)


async def test_a_batch_makes_a_file_and_says_what_is_in_it() -> None:
    applied = await FakeApp().apply(
        None,
        [
            command("add_paragraph", text="Terms\nof payment"),
            command("add_paragraph", text="Signatures"),
            command("add_comment", text="Check the dates"),
        ],
        deadline=1,
    )
    inspection = applied.inspection
    assert inspection.outline == "Terms\nSignatures", "each paragraph's first line"
    assert inspection.text == "Terms\nof payment\n\nSignatures"
    assert inspection.review == {"comments": ["Check the dates"]}
    assert inspection.pages == 1
    assert await FakeApp().inspect(applied.content, deadline=1) == inspection


async def test_every_save_stamps_the_bytes_and_not_the_fingerprint() -> None:
    app = FakeApp()
    source = FakeApp.file("One")
    saved = await app.apply(source, [], deadline=1)
    again = await app.apply(saved.content, [], deadline=1)
    assert len({source, saved.content, again.content}) == 3
    assert saved.inspection.fingerprint == again.inspection.fingerprint
    assert saved.inspection == await app.inspect(source, deadline=1)


@pytest.mark.parametrize(
    ("given", "paragraphs"),
    [
        (command("replace_paragraph", index=1, text="Two, again"), ["One", "Two, again"]),
        (command("delete_paragraph", index=0), ["Two"]),
    ],
)
async def test_commands_change_paragraphs_by_index(
    given: AppCommand, paragraphs: list[str]
) -> None:
    app = FakeApp()
    applied = await app.apply(FakeApp.file("One", "Two"), [given], deadline=1)
    assert applied.inspection.text == "\n\n".join(paragraphs)


@pytest.mark.parametrize(
    "given",
    [
        command("replace_paragraph", index=2, text="x"),
        command("delete_paragraph", index=-1),
        command("add_paragraph"),
        command("format_disk"),
    ],
)
async def test_a_command_that_doesnt_apply_refuses_the_batch(given: AppCommand) -> None:
    with pytest.raises(AppFailed) as refused:
        await FakeApp().apply(FakeApp.file("One", "Two"), [given], deadline=1)
    assert refused.value.failure == "refused"


async def test_it_refuses_a_file_that_isnt_its_own() -> None:
    with pytest.raises(AppFailed, match="refused"):
        await FakeApp().inspect(b"PK\x03\x04 a zip", deadline=1)


async def test_an_outline_is_bounded() -> None:
    inspection = await FakeApp().inspect(FakeApp.file("x" * (OUTLINE_LIMIT + 1)), deadline=1)
    assert len(inspection.outline) == OUTLINE_LIMIT


async def test_it_renders_a_page_as_a_png() -> None:
    app = FakeApp()
    source = FakeApp.file(*(f"Paragraph {n}" for n in range(PAGE + 1)))
    first = await app.render(source, 1, scale=1.0, deadline=1)
    assert first.startswith(b"\x89PNG\r\n\x1a\n")
    assert zlib.crc32(first[-8:-4]) == int.from_bytes(first[-4:]), "an IEND chunk"
    assert first == await app.render(source, 1, scale=1.0, deadline=1), "renders are stable"
    assert first != await app.render(source, 2, scale=1.0, deadline=1)
    for page in (0, 3):
        with pytest.raises(AppFailed, match="page"):
            await app.render(source, page, scale=1.0, deadline=1)


async def test_it_finds_commands_by_name_or_description() -> None:
    found = await FakeApp().commands("PARAGRAPH")
    assert [c.name for c in found] == ["add_paragraph", "replace_paragraph", "delete_paragraph"]
    assert [c.name for c in await FakeApp().commands("comment")] == ["add_comment"]


@pytest.mark.parametrize("failure", ["timeout", "crashed", "too_large", "refused"])
async def test_it_fails_as_it_is_told(failure: Failure) -> None:
    app = FakeApp(fails=failure)
    source = FakeApp.file("One")
    for call in (
        app.apply(source, [], deadline=1),
        app.inspect(source, deadline=1),
        app.render(source, 1, scale=1.0, deadline=1),
    ):
        with pytest.raises(AppFailed) as failed:
            await call
        assert failed.value.failure == failure
