"""FilmCraft's adapter: `.fcproj` video projects edited by FilmCraft's own commands, run headless.

[`Subprocess`][artifactr.files.filmcraft.Subprocess] spawns FilmCraft's CLI on this machine, a
fresh MCP server on stdio for every call, for tests and trusted files. A project is kept only
whole: [`outside`][artifactr.files.filmcraft.outside] names what one draws from files outside it,
which is refused, and what FilmCraft exports from it is not kept (native files ADR-0016).
"""

from artifactr.files.filmcraft.headless import Subprocess
from artifactr.files.filmcraft.project import media_type, outside

__all__ = ["Subprocess", "media_type", "outside"]
