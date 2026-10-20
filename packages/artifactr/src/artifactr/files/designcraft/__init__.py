"""DesignCraft's adapter: layouts, `.idml`, edited by DesignCraft's own commands, run headless.

[`Subprocess`][artifactr.files.designcraft.Subprocess] spawns DesignCraft's CLI on this machine, a
fresh MCP server on stdio for every call, confined to the call's own directory, for tests and
trusted files. A package's format is read from its `mimetype`, by
[`media_type`][artifactr.files.designcraft.media_type], and a layout is saved as IDML, never in
DesignCraft's own format (native files ADR-0009, ADR-0012).
"""

from artifactr.files.designcraft.headless import Subprocess
from artifactr.files.designcraft.package import media_type

__all__ = ["Subprocess", "media_type"]
