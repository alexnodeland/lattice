"""PdfCraft's adapter: `.pdf` documents edited by PdfCraft's own commands, run headless.

[`Subprocess`][artifactr.files.pdfcraft.Subprocess] spawns PdfCraft's CLI on this machine, a
fresh MCP server on stdio for every call, confined to the call's own directory by its one root,
for tests and trusted files. The fingerprint is read from the file itself, by
[`fingerprint`][artifactr.files.pdfcraft.fingerprint]: its digest without the date each save
stamps (lattice RFC-0003, phase 2).
"""

from artifactr.files.pdfcraft.headless import Subprocess
from artifactr.files.pdfcraft.pdf import fingerprint, media_type, outline

__all__ = ["Subprocess", "fingerprint", "media_type", "outline"]
