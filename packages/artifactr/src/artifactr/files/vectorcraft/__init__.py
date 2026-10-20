"""VectorCraft's adapter: SVGs edited by VectorCraft's own commands, run headless.

[`Subprocess`][artifactr.files.vectorcraft.Subprocess] spawns VectorCraft's CLI on this machine, a
fresh MCP server on stdio for every call, confined to the call's own directory, for tests and
trusted files. Whether bytes are an SVG is read from their root element, by
[`media_type`][artifactr.files.vectorcraft.media_type], and nothing else is opened, so nothing is
converted (native files ADR-0009, ADR-0012).
"""

from artifactr.files.vectorcraft.headless import Subprocess
from artifactr.files.vectorcraft.svg import media_type

__all__ = ["Subprocess", "media_type"]
