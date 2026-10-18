"""The crafting apps: each declared once, and run headless through one of two dialects.

[`CRAFTS`][artifactr.files.craft.CRAFTS] declares every app, a
[`Craft`][artifactr.files.craft.Craft] each, as its pinned release offers it. An app's adapter
subclasses one of the two dialects its CLI's MCP server speaks,
[`ToolsDialect`][artifactr.files.craft.ToolsDialect] (WordCraft's) or
[`CommandsDialect`][artifactr.files.craft.CommandsDialect] (PdfCraft's), over
[`Spawn`][artifactr.files.craft.Spawn], which starts the CLI for each call, confined to a
directory of the call's own (native files ADR-0009).
"""

from artifactr.files.craft.commands import PREVIEW, CommandsDialect
from artifactr.files.craft.headless import FOUND, Headless
from artifactr.files.craft.registry import CRAFTS, Bridge, Craft, Dialect, Notice, Reach, Roots
from artifactr.files.craft.spawn import Server, Spawn
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
    "Reach",
    "Roots",
    "Server",
    "Spawn",
    "ToolsDialect",
]
