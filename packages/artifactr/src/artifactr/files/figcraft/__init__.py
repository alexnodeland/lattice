"""FigCraft's adapter: designs, `.figcraft`, edited by FigCraft's own commands, run headless.

[`Subprocess`][artifactr.files.figcraft.Subprocess] spawns FigCraft's CLI on this machine, a fresh
MCP server on stdio for every call, for tests and trusted files: the CLI confines nothing. Whether
bytes are a `.figcraft` is read from its document, by
[`media_type`][artifactr.files.figcraft.media_type], and nothing else is opened, so no save
converts a file (native files ADR-0009, ADR-0012).
"""

from artifactr.files.figcraft.design import media_type
from artifactr.files.figcraft.headless import Subprocess

__all__ = ["Subprocess", "media_type"]
