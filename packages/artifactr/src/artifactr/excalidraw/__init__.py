"""Excalidraw diagrams that people and agents draw on together (lattice RFC-0006).

A diagram is an ordinary JSON artifact, ``excalidraw_diagram``: its elements keyed by their own
ids, each edit a JSON Patch scoped to the elements it touches and guarded by a ``test`` of each
one's version, so concurrent edits to different shapes never conflict and nothing is locked.
Install ``artifactr-ai[excalidraw]`` and import it: nothing else in artifactr imports it, so an
application that draws no diagrams registers no diagram type. The names most applications need
are here; the rest are in the modules:

- :mod:`artifactr.excalidraw.types`: the artifact type, its elements and its limits.
- :mod:`artifactr.excalidraw.patches`: the patch builder, and the rebase after a conflict.
- :mod:`artifactr.excalidraw.checks`: the checks for artifactr's ``Workspaces(checks=...)``.
- :mod:`artifactr.excalidraw.render`: what the agent reads of a diagram.
- :mod:`artifactr.excalidraw.integrations`: the integration that gates it, off by default.
- :mod:`artifactr.excalidraw.wire`: the JSON Schema clients generate their types from.

The agent's tools, the worker that converts and renders, and images in the blob store are
RFC-0006's phase 2 too, and come later; the canvas is phase 3's.
"""

from artifactr.excalidraw.checks import excalidraw_checks
from artifactr.excalidraw.integrations import EXCALIDRAW, excalidraw_key_of
from artifactr.excalidraw.patches import element_patch, rebase, reconcile
from artifactr.excalidraw.render import describe
from artifactr.excalidraw.types import EXCALIDRAW_TYPES, Diagram, DiagramFile, Element, Scene

__all__ = [
    "EXCALIDRAW",
    "EXCALIDRAW_TYPES",
    "Diagram",
    "DiagramFile",
    "Element",
    "Scene",
    "describe",
    "element_patch",
    "excalidraw_checks",
    "excalidraw_key_of",
    "rebase",
    "reconcile",
]
