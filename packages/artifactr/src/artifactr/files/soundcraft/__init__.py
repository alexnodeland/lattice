"""SoundCraft's adapter: `.scraft` audio sessions edited by SoundCraft's own commands, headless.

[`Subprocess`][artifactr.files.soundcraft.Subprocess] spawns SoundCraft's CLI on this machine, a
fresh MCP server on stdio for every call, for tests and trusted files. A session is kept only
whole: [`outside`][artifactr.files.soundcraft.outside] names its audio and video, which are
refused, and what SoundCraft mixes down from it is not kept (native files ADR-0016).
"""

from artifactr.files.soundcraft.headless import Subprocess
from artifactr.files.soundcraft.project import media_type, outside

__all__ = ["Subprocess", "media_type", "outside"]
