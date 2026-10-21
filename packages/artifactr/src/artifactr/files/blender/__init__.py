"""Blender's adapter: 3D scenes, `.blend`, edited by lattice's own commands, run headless.

[`Subprocess`][artifactr.files.blender.Subprocess] starts Blender in the background on the
adapter's script for every call, for tests and trusted files: the script confines nothing. A file
is refused before Blender starts if it holds a text, a driver, animation, a link to another file,
an image, a script node, or any block or struct outside those Blender 5.2 saves for what the
commands make, by [`scan`][artifactr.files.blender.scan] (native files ADR-0015).
"""

from artifactr.files.blender.document import Scanned, fingerprint, scan
from artifactr.files.blender.headless import COMMANDS, Subprocess

__all__ = ["COMMANDS", "Scanned", "Subprocess", "fingerprint", "scan"]
