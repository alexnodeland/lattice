"""The crafting apps, each declared once: what its release offers, and how lattice may use it.

A [`Craft`][artifactr.files.craft.Craft] is a declaration, read from the app's pinned release
(native files ADR-0009): the dialect its CLI speaks, whether that CLI confines the
files it touches, the formats it keeps, whether it renders a page headless, the host surface its
browser build has, and whether lattice keeps its files or only what it exports. Its key,
`files:<name>`, is an integration of lattice-core's registry, which holds its default and its
description, and a test holds the two registries together.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal

from artifactr.files.manifest import (
    DOCX,
    DWG,
    DXF,
    ECPROJ,
    FCPROJ,
    FCSTD,
    FIGCRAFT,
    IDML,
    PDF,
    PPTX,
    PSD,
    SCRAFT,
    SVG,
    XLSX,
)
from lattice_core.integrations import KNOWN, Integration

Dialect = Literal["tools", "commands", "script"]
"""How the CLI is driven: `tools`, an MCP server with a tool for each step (`open_document`,
`batch`, `save_document`, `list_commands`), as WordCraft's; `commands`, an MCP server running
every step as a command through `command_run` and `command_batch`, rendered by `render_preview`,
as PdfCraft's and FilmCraft's (whose servers read a file through `doc_inspect`); `script`, no
server, but a script of the adapter's that the CLI runs for each call, as FreeCAD's `freecadcmd`
(native files ADR-0014)."""

Roots = Literal["split", "single", "none"]
"""How the CLI confines the files it reads and writes: `split`, to a read root and a write root
(`--automation-read-root`, `--automation-write-root`); `single`, to one root for both (`--root`);
`none`, to nothing, so it reads and writes wherever its user can."""

Bridge = Literal["parent", "global"]
"""The host surface of the browser build, as released: `parent`, a `postMessage` bridge to a
same-origin parent page (`?host=parent`) that opens a file and hears its saves and whether it
has unsaved changes; `global`, a JavaScript API on the page's window."""

Reach = Literal["file", "export"]
"""What lattice keeps of the app's work: `file`, the file itself, as a native file that people
and agents edit, which for a project is one that holds every source it draws; `export`, none of
its files, since its work is no file of its own, only, in time, what it renders or exports
(native files ADR-0016)."""


@dataclass(frozen=True)
class Notice:
    """Third-party material a release carries beside its CLI, under a licence of its own.

    Whoever ships the CLI, such as the worker's image, ships its files with it.
    """

    licence: str
    """Its SPDX identifier, such as `CC-BY-SA-4.0`."""

    material: str
    """What it is."""

    attribution: str
    """Whose it is, and where it comes from, as its own attribution gives it."""

    files: tuple[str, ...]
    """The attribution and licence files, as the release's Linux tarball holds them."""


@dataclass(frozen=True)
class Craft:
    """One crafting app: what its pinned release offers, and how lattice may use it."""

    name: str
    """Its name in lowercase, such as `wordcraft`: of its key, its CLI and its repository."""

    title: str
    """Its name as written, such as `WordCraft`."""

    dialect: Dialect
    roots: Roots
    formats: frozenset[str]
    """The media types of the native files it keeps, which its native type holds; none for an
    app whose reach is `export`."""

    render: bool
    """Whether its CLI renders a page as a PNG headless."""

    reach: Reach

    bridge: Bridge | None = None
    notices: tuple[Notice, ...] = ()
    cli: str = field(default="", kw_only=True)
    """Its CLI's name: `<name>-cli` unless given, as every storytold app's is."""

    repository: str = field(default="", kw_only=True)
    """Where it is released on GitHub: `storytold/<name>` unless given."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "cli", self.cli or f"{self.name}-cli")
        object.__setattr__(self, "repository", self.repository or f"storytold/{self.name}")

    @property
    def key(self) -> str:
        """The integration that switches it in a workspace: `files:<name>`."""
        return f"files:{self.name}"

    @property
    def integration(self) -> Integration:
        """Its integration in lattice-core's registry: its default, and its admin's sentence."""
        return KNOWN[self.key]


def _registry(*crafts: Craft) -> Mapping[str, Craft]:
    return MappingProxyType({craft.name: craft for craft in crafts})


CRAFTS: Final = _registry(
    Craft(
        name="wordcraft",
        title="WordCraft",
        dialect="tools",
        roots="split",
        formats=frozenset({DOCX}),
        render=True,
        reach="file",
    ),
    Craft(
        name="gridcraft",
        title="GridCraft",
        dialect="tools",
        roots="none",
        formats=frozenset({XLSX}),
        render=False,
        reach="file",
        bridge="parent",
    ),
    Craft(
        name="deckcraft",
        title="DeckCraft",
        dialect="tools",
        roots="none",
        formats=frozenset({PPTX}),
        render=True,
        reach="file",
    ),
    Craft(
        name="pdfcraft",
        title="PdfCraft",
        dialect="commands",
        roots="single",
        formats=frozenset({PDF}),
        render=True,
        reach="file",
        bridge="parent",
        notices=(
            Notice(
                licence="CC-BY-SA-4.0",
                material="The text detection and recognition models its OCR runs (ocrs-models)",
                attribution=(
                    "Robert Knight, ocrs-models (https://github.com/robertknight/ocrs-models), "
                    "trained on HierText"
                ),
                files=(
                    "share/pdfcraft/models/ATTRIBUTION.txt",
                    "share/pdfcraft/models/text-detection.rten.LICENCE.txt",
                    "share/pdfcraft/models/text-recognition.rten.LICENCE.txt",
                ),
            ),
        ),
    ),
    Craft(
        name="cadcraft",
        title="CADCraft",
        dialect="tools",
        roots="none",
        formats=frozenset({DXF, DWG}),
        render=True,
        reach="file",
        bridge="parent",
    ),
    Craft(
        name="photocraft",
        title="PhotoCraft",
        dialect="commands",
        roots="split",
        formats=frozenset({PSD}),
        render=True,
        reach="file",
    ),
    Craft(
        name="vectorcraft",
        title="VectorCraft",
        dialect="commands",
        roots="split",
        formats=frozenset({SVG}),
        render=True,
        reach="file",
    ),
    Craft(
        name="designcraft",
        title="DesignCraft",
        dialect="tools",
        roots="split",
        formats=frozenset({IDML}),
        render=True,
        reach="file",
    ),
    Craft(
        name="figcraft",
        title="FigCraft",
        dialect="tools",
        roots="none",
        formats=frozenset({FIGCRAFT}),
        render=True,
        reach="file",
    ),
    Craft(
        name="freecad",
        title="FreeCAD",
        dialect="script",
        roots="none",
        formats=frozenset({FCSTD}),
        render=True,
        reach="file",
        cli="freecadcmd",
        repository="FreeCAD/FreeCAD",
    ),
    Craft(
        name="filmcraft",
        title="FilmCraft",
        dialect="commands",
        roots="none",
        formats=frozenset({FCPROJ}),
        render=True,
        reach="file",
    ),
    Craft(
        name="effectcraft",
        title="EffectCraft",
        dialect="commands",
        roots="split",
        formats=frozenset({ECPROJ}),
        render=True,
        reach="file",
        bridge="global",
    ),
    Craft(
        name="soundcraft",
        title="SoundCraft",
        dialect="tools",
        roots="split",
        formats=frozenset({SCRAFT}),
        render=False,
        reach="file",
    ),
    Craft(
        name="lightcraft",
        title="LightCraft",
        dialect="commands",
        roots="none",
        formats=frozenset(),
        render=True,
        reach="export",
        bridge="global",
    ),
)
"""The crafting apps, by name, read-only: what each pinned release offers, checked on
2026-10-18 against its CLI's own MCP tools and options; and FreeCAD, a third party's, checked
on 2026-10-20 against its console (native files ADR-0014)."""
