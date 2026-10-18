"""The `commands` dialect, against a stand-in for a CLI that speaks it, as PdfCraft's does.

`fake_commands_cli.py` is the stand-in, so these run on every pull request; each app's own
adapter is run against the app itself by its live tests.
"""

import hashlib
import json
import stat
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import JsonValue

from artifactr.files.app import App, AppCommand, AppFailed, Inspection
from artifactr.files.craft import CommandsDialect, Craft, Roots, Server

FAKE = Path(__file__).with_name("fake_commands_cli.py")
PNG = b"\x89PNG\r\n\x1a\n"

TOOLCRAFT = Craft(
    name="toolcraft",
    title="ToolCraft",
    dialect="commands",
    roots="single",
    formats=frozenset({"application/json"}),
    render=True,
    reach="file",
)


class Toolcraft(CommandsDialect):
    """The stand-in's adapter: its files' pages are their words."""

    craft: ClassVar[Craft] = TOOLCRAFT
    extension: ClassVar[str] = ".json"
    new_command: ClassVar[str | None] = "file.new"

    async def inspection(self, server: Server, document: JsonValue, content: bytes) -> Inspection:
        listed = await server.json("doc_inspect")
        assert isinstance(listed, dict)
        documents = listed["documents"]
        assert isinstance(documents, list)
        (document,) = documents
        assert isinstance(document, dict)
        pages = document["pages"]
        assert isinstance(pages, list)
        words = [str(page) for page in pages]
        return Inspection(
            fingerprint=hashlib.sha256(json.dumps(words).encode()).hexdigest(),
            text="\n".join(words),
            pages=len(words),
        )


class Blankless(Toolcraft):
    new_command: ClassVar[str | None] = None


class Unnamed(Toolcraft):
    handle: ClassVar[str | None] = None


Make = Callable[..., Toolcraft]


@pytest.fixture
def spawn(tmp_path: Path) -> Callable[..., Toolcraft]:
    """Make an adapter over the stand-in, misbehaving as `mode` says."""

    def spawn(
        mode: str = "",
        *,
        adapter: type[Toolcraft] = Toolcraft,
        roots: Roots = "single",
        render: bool = True,
        trusted: bool = False,
    ) -> Toolcraft:
        cli = tmp_path / f"toolcraft-cli{mode}"
        cli.write_text(
            f'#!/bin/sh\nexport FAKE_ARGS="{tmp_path / "args"}"\n'
            f'exec "{sys.executable}" -I "{FAKE}" --mode "{mode}" "$@"\n'
        )
        cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
        configured = type(
            adapter.__name__, (adapter,), {"craft": replace(TOOLCRAFT, roots=roots, render=render)}
        )
        return configured(cli, version="1.0.0", trusted=trusted)

    return spawn


def page(text: str) -> AppCommand:
    return AppCommand(name="page.add", args={"text": text})


def source(*pages: str) -> bytes:
    return json.dumps({"pages": list(pages), "saves": 0}).encode()


def test_it_is_an_app_named_by_its_craft(spawn: Make) -> None:
    app: App = spawn()
    assert (app.name, app.version, app.build) == ("toolcraft", "1.0.0", None)
    assert (app.talk, app.integration) == ("save", "files:toolcraft")


async def test_a_batch_on_a_blank_file_names_the_open_document(spawn: Make) -> None:
    applied = await spawn().apply(None, [page("One"), page("Two")], deadline=20)
    assert json.loads(applied.content) == {"pages": ["One", "Two"], "saves": 1}
    assert (applied.inspection.text, applied.inspection.pages) == ("One\nTwo", 2)


async def test_a_file_is_opened_saved_and_read(spawn: Make) -> None:
    app = spawn()
    applied = await app.apply(source("One"), [page("Two")], deadline=20)
    assert json.loads(applied.content)["pages"] == ["One", "Two"]
    assert (await app.inspect(applied.content, deadline=20)) == applied.inspection
    again = await app.apply(applied.content, [], deadline=20)
    assert again.content != applied.content, "every save stamps the file"
    assert again.inspection == applied.inspection


async def test_an_app_that_makes_no_blank_file_refuses_one(spawn: Make) -> None:
    with pytest.raises(AppFailed, match="ToolCraft makes no blank file headless") as refused:
        await spawn(adapter=Blankless).apply(None, [], deadline=20)
    assert refused.value.failure == "refused"


async def test_an_open_that_names_no_document_is_a_crash(spawn: Make) -> None:
    with pytest.raises(AppFailed, match=r"file\.open named no document as doc") as crashed:
        await spawn("bare").apply(source("One"), [], deadline=20)
    assert crashed.value.failure == "crashed"


async def test_a_server_whose_commands_name_no_document_is_asked_without_one(spawn: Make) -> None:
    with pytest.raises(AppFailed, match="no document None") as refused:
        await spawn("bare", adapter=Unnamed).apply(source("One"), [], deadline=20)
    assert refused.value.failure == "refused", "the stand-in itself wants one named"


async def test_an_open_that_replies_with_no_json_is_a_crash(spawn: Make) -> None:
    with pytest.raises(AppFailed, match="command_run replied with no JSON") as crashed:
        await spawn("opaque").inspect(source("One"), deadline=20)
    assert crashed.value.failure == "crashed"


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("", 'nope: command "nope" has no headless tool'),
        ("garbled", '"failed": 1'),
        ("quiet", '"failed": 1'),
        ("lenient", 'nope: command "nope" has no headless tool'),
    ],
)
async def test_a_command_that_fails_refuses_the_batch_and_is_named(
    spawn: Make, mode: str, message: str
) -> None:
    with pytest.raises(AppFailed, match=message) as refused:
        await spawn(mode).apply(source(), [page("One"), AppCommand(name="nope")], deadline=20)
    assert refused.value.failure == "refused"


async def test_it_renders_a_page_as_a_png(spawn: Make) -> None:
    app = spawn()
    assert (await app.render(source("One"), 1, scale=0.0001, deadline=20)).startswith(PNG)
    with pytest.raises(AppFailed, match="no page 2") as refused:
        await app.render(source("One"), 2, scale=1, deadline=20)
    assert refused.value.failure == "refused"


async def test_an_app_that_renders_nothing_headless_refuses_before_it_starts(
    spawn: Make, tmp_path: Path
) -> None:
    app = spawn(render=False)
    with pytest.raises(AppFailed, match="ToolCraft renders no page headless") as refused:
        await app.render(source("One"), 1, scale=1, deadline=20)
    assert refused.value.failure == "refused"
    assert not (tmp_path / "args").exists(), "no CLI was started"


@pytest.mark.parametrize("mode", ["", "bare"])
async def test_it_finds_ten_commands_at_most(spawn: Make, mode: str) -> None:
    found = await spawn(mode).commands("page")
    assert len(found) == 10, "the stand-in repeats each match five times"
    added, rotated = found[0], found[1]
    assert added.signature == 'page.add {"properties": {"text": {"type": "string"}}}'
    assert added.description == "Add a page (Pages)"
    assert (rotated.signature, rotated.description) == (
        "page.rotate",
        "Rotate pages (Pages > Rotate)",
    )
    about = (await spawn(mode).commands("about"))[0]
    assert (about.signature, about.description) == ("help.about {}", "About")


async def test_a_list_that_isnt_commands_is_a_crash(spawn: Make) -> None:
    with pytest.raises(AppFailed, match="command_list replied with no commands") as crashed:
        await spawn("listless").commands("page")
    assert crashed.value.failure == "crashed"


@pytest.mark.parametrize(
    ("roots", "given"),
    [
        ("single", ["--root", "{root}"]),
        ("split", ["--automation-read-root", "{root}/in", "--automation-write-root", "{root}/out"]),
        ("none", []),
    ],
)
async def test_the_cli_is_confined_by_the_roots_it_takes(
    spawn: Make, tmp_path: Path, roots: Roots, given: list[str]
) -> None:
    await spawn(roots=roots, trusted=True).commands("page")
    mode, command, *rest = json.loads((tmp_path / "args").read_text())[1:]
    assert (mode, command) == ("", "mcp")
    root = str(Path(rest[1]).parent) if roots == "split" else (rest[1] if rest else "")
    assert rest == [argument.format(root=root) for argument in given]


def test_a_cli_that_confines_nothing_needs_trusted_files(spawn: Make) -> None:
    with pytest.raises(ValueError, match="toolcraft-cli confines no file it reads or writes"):
        spawn(roots="none")


def test_an_adapter_that_reads_files_names_its_craft() -> None:
    with pytest.raises(TypeError, match="Nameless reads files, so it names its craft"):

        class Nameless(CommandsDialect):
            async def inspection(
                self, server: Server, document: JsonValue, content: bytes
            ) -> Inspection:
                raise NotImplementedError
