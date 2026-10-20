"""FreeCAD's adapter, against a stand-in for `freecadcmd` running its script.

`fake_cli.py` is the stand-in, so these run on every pull request; `test_live.py` runs the same
calls against FreeCAD itself.
"""

import ast
import io
import stat
import sys
import zipfile
from pathlib import Path

import pytest

from artifactr.files.app import App, AppCommand, AppFailed
from artifactr.files.freecad import COMMANDS, Subprocess, fingerprint
from artifactr.files.freecad.headless import SCRIPT
from artifactr.files.manifest import FCSTD
from tests.files.freecad.documents import fcstd, obj, xml

FAKE = Path(__file__).with_name("fake_cli.py")
PNG = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def freecad(tmp_path: Path) -> Subprocess:
    cli = tmp_path / "freecadcmd"
    cli.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I "{FAKE}" "$@"\n')
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    return Subprocess(cli, version="1.1.4", trusted=True)


def box() -> AppCommand:
    return AppCommand(name="box", args={"length": 1, "width": 1, "height": 1})


def test_it_is_an_app_that_talks_only_on_save_and_confines_nothing(freecad: Subprocess) -> None:
    app: App = freecad
    assert (app.name, app.version, app.build, app.talk) == ("freecad", "1.1.4", None, "save")
    assert app.integration == "files:freecad"
    with pytest.raises(ValueError, match="trusted=True"):
        Subprocess("freecadcmd", version="1.1.4")


async def test_a_batch_on_a_blank_document_saves_it_and_reads_it(freecad: Subprocess) -> None:
    applied = await freecad.apply(None, [box(), box()], deadline=10)
    assert applied.inspection.outline == "Box0 (Part::Box)\nBox1 (Part::Box)"
    assert applied.inspection.text == "Sheet.A1: 42"
    assert (applied.inspection.pages, applied.inspection.media_type) == (1, FCSTD)
    assert applied.inspection.fingerprint == fingerprint(applied.content)


async def test_a_save_keeps_the_label_and_the_gui_and_twice_is_a_fixpoint(
    freecad: Subprocess,
) -> None:
    gui = "<Document><ViewProviderData/></Document>"
    source = fcstd(xml(obj("Box", "Part::Box"), label="Bracket"), **{"GuiDocument.xml": gui})
    once = await freecad.apply(source, [], deadline=10)
    twice = await freecad.apply(once.content, [], deadline=10)
    with zipfile.ZipFile(io.BytesIO(once.content)) as archive:
        assert 'value="Bracket"' in archive.read("Document.xml").decode()
        assert archive.read("GuiDocument.xml").decode() == gui
    assert twice.inspection == once.inspection
    assert once.inspection.fingerprint == fingerprint(source), "only the time a save writes"


async def test_a_command_it_refuses_refuses_the_batch(freecad: Subprocess) -> None:
    with pytest.raises(AppFailed, match="no command 'shell'") as failed:
        await freecad.apply(None, [box(), AppCommand(name="shell")], deadline=10)
    assert failed.value.failure == "refused"


async def test_a_document_holding_python_is_refused_before_freecad_starts(
    freecad: Subprocess,
) -> None:
    python = fcstd(xml(obj("Py", "Part::FeaturePython")))
    for call in (
        freecad.apply(python, [], deadline=10),
        freecad.inspect(python, deadline=10),
        freecad.render(python, 1, scale=1, deadline=10),
    ):
        with pytest.raises(AppFailed, match="holds Python"):
            await call


async def test_inspect_reads_the_source(freecad: Subprocess) -> None:
    source = fcstd()
    inspection = await freecad.inspect(source, deadline=10)
    assert inspection.outline == "Box (Part::Box)"
    assert inspection.fingerprint == fingerprint(source)


async def test_page_one_is_drawn_and_no_other(freecad: Subprocess) -> None:
    assert await freecad.render(fcstd(), 1, scale=0.5, deadline=10) == PNG
    with pytest.raises(AppFailed, match="no page 2"):
        await freecad.render(fcstd(), 2, scale=1, deadline=10)


async def test_a_save_or_a_page_it_doesnt_write_is_a_crash(freecad: Subprocess) -> None:
    unsaved = fcstd(xml(label="Unsaved"))
    with pytest.raises(AppFailed, match="saved no document") as failed:
        await freecad.apply(unsaved, [], deadline=10)
    assert failed.value.failure == "crashed"
    with pytest.raises(AppFailed, match="drew no page"):
        await freecad.render(unsaved, 1, scale=1, deadline=10)


async def test_its_commands_are_found_with_no_cli_started(freecad: Subprocess) -> None:
    assert [c.name for c in await freecad.commands("sketch")] == [
        "sketch",
        "sketch.line",
        "sketch.circle",
        "sketch.constraint",
        "extrude",
    ]
    assert len(await freecad.commands("")) == 10


def test_its_commands_are_the_scripts() -> None:
    """The script runs in FreeCAD alone, so its table is read from its source."""
    tree = ast.parse(SCRIPT.read_text())
    (table,) = [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "COMMANDS" for t in node.targets)
    ]
    assert isinstance(table, ast.Dict)
    assert [ast.literal_eval(key) for key in table.keys if key] == [c.name for c in COMMANDS]
