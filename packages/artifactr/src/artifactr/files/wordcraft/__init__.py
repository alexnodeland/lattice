"""WordCraft's adapter: `.docx` files edited by WordCraft's own commands, run headless.

[`Subprocess`][artifactr.files.wordcraft.Subprocess] spawns WordCraft's CLI on this machine, a
fresh MCP server on stdio for every call, for tests and trusted files. The fingerprint is read
from the file itself, by [`fingerprint`][artifactr.files.wordcraft.fingerprint]: the digest of
its parts without the one each save stamps (lattice RFC-0003, phase 2).
"""

from artifactr.files.wordcraft.docx import STAMPED, fingerprint, outline
from artifactr.files.wordcraft.headless import Subprocess

__all__ = ["STAMPED", "Subprocess", "fingerprint", "outline"]
