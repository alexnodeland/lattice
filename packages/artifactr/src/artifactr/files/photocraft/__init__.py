"""PhotoCraft's adapter: `.psd` documents edited by PhotoCraft's own commands, run headless.

[`Subprocess`][artifactr.files.photocraft.Subprocess] spawns PhotoCraft's CLI on this machine, a
fresh MCP server on stdio for every call, for tests and trusted files. A document's format is
read from its header, by [`media_type`][artifactr.files.photocraft.media_type]: a `.psb` isn't a
`.psd`, and a save never makes it one (native files ADR-0009, ADR-0012).
"""

from artifactr.files.photocraft.headless import Subprocess
from artifactr.files.photocraft.psd import media_type

__all__ = ["Subprocess", "media_type"]
