"""FreeCAD's adapter: 3D models, `.FCStd`, edited by lattice's own commands, run headless.

[`Subprocess`][artifactr.files.freecad.Subprocess] starts FreeCAD's console, `freecadcmd`, on
the adapter's script for every call, for tests and trusted files: the script confines nothing. A
document is refused before FreeCAD starts if it holds a Python feature or proxy, a link to
another file, or an object outside FreeCAD's C++ workbenches, by
[`scan`][artifactr.files.freecad.scan] (native files ADR-0014).
"""

from artifactr.files.freecad.document import Scanned, fingerprint, scan
from artifactr.files.freecad.headless import COMMANDS, Subprocess

__all__ = ["COMMANDS", "Scanned", "Subprocess", "fingerprint", "scan"]
