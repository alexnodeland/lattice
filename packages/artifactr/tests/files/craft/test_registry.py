"""The crafting apps' registry: one declaration each, held to lattice-core's and to the pins."""

from pathlib import Path

import pytest

from artifactr.files.craft import CRAFTS, Craft
from artifactr.files.manifest import (
    BLEND,
    DOCX,
    FCSTD,
    CadModel,
    Design,
    Drawing,
    LayeredImage,
    NativeFile,
    PageLayout,
    Scene,
    VectorImage,
    WordDocument,
)
from artifactr.files.wordcraft import Subprocess
from lattice_core.integrations import KNOWN

PINS = Path(__file__).parents[5] / "scripts" / "crafts"
BRAND = "artcraft"
"""The apps' brand, whose licence lets its name appear only in the official builds."""


def test_lattice_cores_registry_declares_each_crafting_app_as_its_descriptor_does() -> None:
    declared = {key: known for key, known in KNOWN.items() if key.startswith("files:")}
    assert list(declared) == [craft.key for craft in CRAFTS.values()], "in the same order"
    assert all(craft.integration is declared[craft.key] for craft in CRAFTS.values())


def test_only_wordcraft_is_on_by_default() -> None:
    assert [c.name for c in CRAFTS.values() if c.integration.default] == ["wordcraft"]


def test_a_cli_that_confines_nothing_is_never_on_by_default() -> None:
    unconfined = {craft.name for craft in CRAFTS.values() if craft.roots == "none"}
    assert unconfined == {
        "gridcraft",
        "deckcraft",
        "cadcraft",
        "figcraft",
        "freecad",
        "blender",
        "filmcraft",
        "lightcraft",
    }
    assert not any(CRAFTS[name].integration.default for name in unconfined)


def test_each_app_is_pinned() -> None:
    assert sorted(path.stem for path in PINS.glob("*.sha256")) == sorted(CRAFTS)


THIRD_PARTIES = {"freecad", "blender"}
STORYTOLDS = [craft for craft in CRAFTS.values() if craft.name not in THIRD_PARTIES]


@pytest.mark.parametrize("craft", STORYTOLDS, ids=[craft.name for craft in STORYTOLDS])
def test_each_storytold_app_is_named_as_its_release_is(craft: Craft) -> None:
    assert craft.name == craft.title.lower()
    assert (craft.key, craft.cli, craft.repository) == (
        f"files:{craft.name}",
        f"{craft.name}-cli",
        f"storytold/{craft.name}",
    )
    description = craft.integration.description
    assert description.startswith(f"{craft.title}: ")
    assert BRAND not in f"{craft.title} {description}".lower()
    for notice in craft.notices:
        assert BRAND not in f"{notice.material} {notice.attribution}".lower()


def test_freecad_is_a_third_partys_run_by_a_script_its_console_runs() -> None:
    """FreeCAD is the FreeCAD project's, under no brand licence, named plainly (ADR-0014)."""
    freecad = CRAFTS["freecad"]
    assert (freecad.key, freecad.cli, freecad.repository) == (
        "files:freecad",
        "freecadcmd",
        "FreeCAD/FreeCAD",
    )
    assert (freecad.dialect, freecad.roots, freecad.formats) == ("script", "none", {FCSTD})
    assert freecad.integration.description.startswith("FreeCAD: ")
    assert [c.name for c in CRAFTS.values() if c.dialect == "script"] == ["freecad", "blender"]


def test_blender_is_a_third_partys_run_by_a_script_in_its_background_mode() -> None:
    """Blender is the Blender Foundation's, under no brand licence, named plainly (ADR-0015)."""
    blender = CRAFTS["blender"]
    assert (blender.key, blender.cli, blender.repository) == (
        "files:blender",
        "blender",
        "blender/blender",
    )
    assert (blender.dialect, blender.roots, blender.formats) == ("script", "none", {BLEND})
    assert blender.integration.description.startswith("Blender: ")


def test_no_two_apps_keep_one_format_and_an_app_that_exports_keeps_none() -> None:
    kept = [media_type for craft in CRAFTS.values() for media_type in craft.formats]
    assert len(kept) == len(set(kept))
    assert all(not craft.formats for craft in CRAFTS.values() if craft.reach == "export")
    assert {c.name for c in CRAFTS.values() if c.reach == "export"} == {
        "filmcraft",
        "effectcraft",
        "soundcraft",
        "lightcraft",
    }


def test_pdfcrafts_ocr_models_carry_their_attribution() -> None:
    (notice,) = CRAFTS["pdfcraft"].notices
    assert notice.licence == "CC-BY-SA-4.0"
    assert "share/pdfcraft/models/ATTRIBUTION.txt" in notice.files
    assert [craft.name for craft in CRAFTS.values() if craft.notices] == ["pdfcraft"]


def test_wordcraft_is_its_descriptors() -> None:
    assert Subprocess.craft is CRAFTS["wordcraft"]
    assert CRAFTS["wordcraft"].formats == {DOCX}


@pytest.mark.parametrize(
    ("app", "native"),
    [
        ("wordcraft", WordDocument),
        ("cadcraft", Drawing),
        ("photocraft", LayeredImage),
        ("vectorcraft", VectorImage),
        ("designcraft", PageLayout),
        ("figcraft", Design),
        ("freecad", CadModel),
        ("blender", Scene),
    ],
)
def test_an_apps_formats_are_its_native_types(app: str, native: type[NativeFile]) -> None:
    assert CRAFTS[app].formats == native.formats
