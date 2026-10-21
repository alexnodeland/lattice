"""The crafting apps: each declared once, and run headless through one of three dialects.

[`CRAFTS`][artifactr.files.craft.CRAFTS] declares every app, a
[`Craft`][artifactr.files.craft.Craft] each, as its pinned release offers it. An app's adapter
subclasses one of the two dialects its CLI's MCP server speaks,
[`ToolsDialect`][artifactr.files.craft.ToolsDialect] (WordCraft's) or
[`CommandsDialect`][artifactr.files.craft.CommandsDialect] (PdfCraft's), over
[`Spawn`][artifactr.files.craft.Spawn], which starts the CLI for each call, confined to a
directory of the call's own (native files ADR-0009). [`Package`][artifactr.files.craft.Package]
reads what an adapter reads of a zip package itself, as the Office Open XML apps' files are. An
app with no server, FreeCAD, runs a script of its adapter's for each call instead, through
[`Script`][artifactr.files.craft.Script] (native files ADR-0014).
"""

from artifactr.files.craft.commands import PREVIEW, CommandsDialect
from artifactr.files.craft.headless import FOUND, Headless
from artifactr.files.craft.package import Package
from artifactr.files.craft.registry import CRAFTS, Bridge, Craft, Dialect, Notice, Reach, Roots
from artifactr.files.craft.script import Ran, Script
from artifactr.files.craft.spawn import Server, Spawn, reply_text
from artifactr.files.craft.tools import ToolsDialect

__all__ = [
    "CRAFTS",
    "FOUND",
    "PREVIEW",
    "Bridge",
    "CommandsDialect",
    "Craft",
    "Dialect",
    "Headless",
    "Notice",
    "Package",
    "Ran",
    "Reach",
    "Roots",
    "Script",
    "Server",
    "Spawn",
    "ToolsDialect",
    "reply_text",
]
