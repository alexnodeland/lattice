"""CADCraft's adapter: drawings, `.dxf` and `.dwg`, edited by CADCraft's own commands, run headless.

[`Subprocess`][artifactr.files.cadcraft.Subprocess] spawns CADCraft's CLI on this machine, a fresh
MCP server on stdio for every call, for tests and trusted files: the CLI confines nothing. A
drawing's format is read from its first bytes, by
[`media_type`][artifactr.files.cadcraft.media_type], and a save keeps it (native files ADR-0009,
ADR-0012).
"""

from artifactr.files.cadcraft.drawing import media_type
from artifactr.files.cadcraft.headless import Subprocess

__all__ = ["Subprocess", "media_type"]
