"""EffectCraft's adapter: `.ecproj` motion graphics edited by EffectCraft's own commands, headless.

[`Subprocess`][artifactr.files.effectcraft.Subprocess] spawns EffectCraft's CLI on this machine,
a fresh MCP server on stdio for every call, for tests and trusted files. A project is kept only
whole: [`outside`][artifactr.files.effectcraft.outside] names its footage, which is refused, and
what EffectCraft renders from it is not kept (native files ADR-0016).
"""

from artifactr.files.effectcraft.headless import Subprocess
from artifactr.files.effectcraft.project import media_type, outside

__all__ = ["Subprocess", "media_type", "outside"]
