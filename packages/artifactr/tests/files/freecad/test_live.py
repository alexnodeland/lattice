"""FreeCAD itself, run headless from the pinned `freecadcmd`: the adapter and its script live.

These run only where `ARTIFACTR_TEST_CRAFT` is `freecad` and `ARTIFACTR_TEST_CRAFT_CLI` names
`freecadcmd`, as `moon run artifactr:fidelity` sets them from `scripts/craft freecad cli`. Its
fidelity report is the corpus harness's, `tests/files/corpus/test_fidelity.py`. Between them,
every command and every step of `script.py` runs, which no pull request's coverage measures.
"""

import base64
import io
import os
import pickle
import subprocess
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.freecad import COMMANDS, Subprocess, scan
from artifactr.files.freecad.headless import PAPER
from artifactr.files.manifest import FCSTD
from tests.files.app.png import pixels
from tests.files.corpus.freecad.corpus import CORPUS, python
from tests.files.corpus.harness import pinned

pytestmark = [pytest.mark.craft("freecad"), pytest.mark.timeout(120)]
DEADLINE = 20
VERSION = pinned("freecad")
"""The version scripts/craft pins, which the CLI must be."""


@pytest.fixture(scope="module")
def freecad() -> Subprocess:
    return Subprocess(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], version=VERSION, trusted=True)


def command(called: str, /, **args: object) -> AppCommand:
    return AppCommand.model_validate({"name": called, "args": args})


EVERY = [
    command("box", length=10, width=10, height=10),
    command("cylinder", radius=3, height=12, at=[5, 5, -1], name="Hole"),
    command("boolean", operation="cut", base="Box", tool="Hole"),
    command("sphere", radius=2, at=[30, 0, 0]),
    command("cone", radius1=3, radius2=1, height=4, at=[0, 30, 0]),
    command("boolean", operation="fuse", base="Sphere", tool="Cone", name="Pair"),
    command("sketch", plane="XZ", name="Profile"),
    command("sketch.line", sketch="Profile", start=[0, 0], end=[8, 0]),
    command("sketch.line", sketch="Profile", start=[8, 0], end=[8, 4]),
    command("sketch.line", sketch="Profile", start=[8, 4], end=[0, 0]),
    command("sketch.constraint", sketch="Profile", type="Coincident", values=[0, 2, 1, 1]),
    command("sketch.constraint", sketch="Profile", type="Coincident", values=[1, 2, 2, 1]),
    command("sketch.constraint", sketch="Profile", type="Coincident", values=[2, 2, 0, 1]),
    command("sketch.constraint", sketch="Profile", type="Horizontal", values=[0]),
    command("sketch.constraint", sketch="Profile", type="DistanceX", values=[0, 1, 0, 2, 8.0]),
    command("extrude", sketch="Profile", length=2),
    command("sketch", name="Disc"),
    command("sketch.circle", sketch="Disc", center=[50, 50], radius=4),
    command("remove", object="Disc"),
    command("move", object="Extrude", at=[0, -20, 0], axis=[0, 0, 1], angle=45),
    command("sheet", name="Sizes"),
    command("sheet.set", sheet="Sizes", cell="A1", content="12"),
    command("sheet.alias", sheet="Sizes", cell="A1", alias="size"),
    command("set", object="Cut", property="Label", value="Block"),
    command("set", object="Sphere", property="Radius", value=2.5),
]


async def test_every_command_builds_a_model_that_saves_reads_and_draws(
    freecad: Subprocess,
) -> None:
    assert {c.name for c in COMMANDS} == {c.name for c in EVERY}
    applied = await freecad.apply(None, EVERY, deadline=DEADLINE)
    inspection = applied.inspection
    assert inspection.media_type == FCSTD
    assert "Block (Part::Cut)" in inspection.outline
    assert "Disc" not in inspection.outline
    assert inspection.text == "Sizes.A1: 12"
    png = await freecad.render(applied.content, 1, scale=0.25, deadline=DEADLINE)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    again = await freecad.apply(applied.content, [], deadline=DEADLINE)
    assert again.inspection == inspection, "a save of a saved model changes nothing it reads"


@pytest.mark.parametrize(
    ("commands", "why"),
    [
        ([command("python", code="import os")], "no command 'python'"),
        ([command("box", length=-1, width=1, height=1)], "length must be more than 0"),
        ([command("box", length=1, width=1, height=1, shell=True)], "unknown argument shell"),
        (
            [
                command("box", length=1, width=1, height=1),
                command("set", object="Box", property="Proxy", value=1),
            ],
            "no property Proxy that can be set",
        ),
        (
            [
                command("box", length=1, width=1, height=1),
                command("set", object="Box", property="Placement", value=1),
            ],
            "no property Placement that can be set",
        ),
        ([command("boolean", operation="cut", base="A", tool="B")], "no object A"),
        ([command("sheet.set", sheet="Nope", cell="A1", content="1")], "no object Nope"),
    ],
)
async def test_what_the_commands_dont_allow_is_refused(
    freecad: Subprocess, commands: list[AppCommand], why: str
) -> None:
    with pytest.raises(AppFailed, match=why) as refused:
        await freecad.apply(None, commands, deadline=DEADLINE)
    assert refused.value.failure == "refused"


async def test_an_empty_model_is_drawn_as_white_paper_and_has_no_page_two(
    freecad: Subprocess,
) -> None:
    """If the script refuses an empty model in other words, it is refused here, and fails."""
    blank = await freecad.apply(None, [], deadline=DEADLINE)
    png = await freecad.render(blank.content, 1, scale=0.25, deadline=DEADLINE)
    assert pixels(png) == (256, 256, PAPER)
    with pytest.raises(AppFailed, match="no page 2") as refused:
        await freecad.render(CORPUS.source("primitives"), 2, scale=1, deadline=DEADLINE)
    assert refused.value.failure == "refused"


async def test_its_commands_are_found(freecad: Subprocess) -> None:
    assert [c.name for c in await freecad.commands("sheet")] == [
        "sheet",
        "sheet.set",
        "sheet.alias",
    ]


class _Shell:
    """What a pickled proxy runs if it is ever unpickled: it leaves a mark in `$HOME`."""

    def __reduce__(self) -> tuple[Callable[..., object], tuple[str]]:
        return (os.system, ('touch "$HOME/pickled"',))


@pytest.mark.parametrize(
    ("proxy", "said"),
    [
        (
            f'<Python value="{base64.b64encode(pickle.dumps(_Shell(), protocol=2)).decode()}"'
            ' encoded="yes"/>',
            "unsupported serialisation",
        ),
        (
            '<Python value="e30=" encoded="yes" json="yes" module="this" class="Thing"/>',
            "blocked import of module 'this'",
        ),
    ],
    ids=["a-pickle", "a-module-outside-freecads-own"],
)
def test_freecad_itself_runs_no_pickle_and_imports_no_module_outside_its_own(
    tmp_path: Path, proxy: str, said: str
) -> None:
    """The guards behind the scan, in FreeCAD's own restore: a raised pin must keep them."""
    path = tmp_path / "python.FCStd"
    path.write_bytes(python(proxy))
    script = tmp_path / "open.py"
    script.write_text(f"import FreeCAD\nFreeCAD.openDocument({str(path)!r})\n")
    printed = subprocess.run(
        [os.environ["ARTIFACTR_TEST_CRAFT_CLI"], "--safe-mode", str(script)],
        env={"HOME": str(tmp_path), "LANG": "C.UTF-8", "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        errors="replace",
        timeout=60,
        check=False,
    )
    assert said in printed.stdout + printed.stderr
    assert not (tmp_path / "pickled").exists()


async def test_a_file_freecads_gui_saved_keeps_its_colours_and_then_its_fingerprint(
    freecad: Subprocess,
) -> None:
    """Its first save by the console rewrites what FreeCAD's GUI wrote; the next is a fixpoint."""
    source = (Path(__file__).with_name("gui_made.FCStd")).read_bytes()
    once = await freecad.apply(source, [], deadline=DEADLINE)
    twice = await freecad.apply(once.content, [], deadline=DEADLINE)
    assert twice.inspection == once.inspection
    with zipfile.ZipFile(io.BytesIO(once.content)) as archive:
        assert {"GuiDocument.xml", "ShapeAppearance"} <= set(archive.namelist())


def opened(tmp_path: Path, content: bytes) -> list[str]:
    """Each object FreeCAD opens from `content`, its name, type and whether its shape is there."""
    path = tmp_path / "opened.FCStd"
    path.write_bytes(content)
    script = tmp_path / "opened.py"
    script.write_text(
        "import FreeCAD\n"
        f"document = FreeCAD.openDocument({str(path)!r})\n"
        "for o in document.Objects:\n"
        "    shape = getattr(o, 'Shape', None)\n"
        "    print('OPENED', o.Name, o.TypeId, shape is not None and not shape.isNull())\n"
    )
    printed = subprocess.run(
        [os.environ["ARTIFACTR_TEST_CRAFT_CLI"], "--safe-mode", str(script)],
        env={"HOME": str(tmp_path), "LANG": "C.UTF-8", "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        errors="replace",
        timeout=60,
        check=False,
    )
    return [
        line.removeprefix("OPENED ") for line in printed.stdout.splitlines() if "OPENED" in line
    ]


def test_freecad_takes_the_first_entry_as_the_document_whatever_its_name(tmp_path: Path) -> None:
    """Why the scan writes Document.xml first, and refuses a part nothing names."""
    hostile = CORPUS.hostile_file("document_not_first")
    assert "Py App::FeaturePython False" in opened(tmp_path, hostile), "a.txt, read first"
    with pytest.raises(AppFailed, match=r"nothing names a\.txt"):
        scan(hostile, 1 << 28)


def test_freecad_reads_parts_only_in_the_order_it_asks_for_them(tmp_path: Path) -> None:
    """Why the scan orders parts as Document.xml names them, not by name."""
    canonical = scan(CORPUS.source("booleans"), 1 << 28).content
    with zipfile.ZipFile(io.BytesIO(canonical)) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    by_name = io.BytesIO()
    with zipfile.ZipFile(by_name, "w") as archive:
        archive.writestr("Document.xml", parts.pop("Document.xml"))
        for name in sorted(parts):
            archive.writestr(name, parts[name])
    assert all(line.endswith("True") for line in opened(tmp_path, canonical))
    assert any(line.endswith("False") for line in opened(tmp_path, by_name.getvalue()))
