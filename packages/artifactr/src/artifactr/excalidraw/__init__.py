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
- :mod:`artifactr.excalidraw.converter`: what draws and renders: the worker's client, and a fake.
- :mod:`artifactr.excalidraw.tools`: the agent's toolset.
- :mod:`artifactr.excalidraw.sweep`: the tombstone sweep.

The worker that converts and renders is stackr's to run; the canvas is phase 3's.
"""

from artifactr.excalidraw.checks import excalidraw_checks
from artifactr.excalidraw.converter import (
    ConversionFailed,
    Converted,
    Converter,
    FakeConverter,
    WorkerConverter,
)
from artifactr.excalidraw.integrations import EXCALIDRAW, excalidraw_key_of
from artifactr.excalidraw.patches import element_patch, rebase, reconcile
from artifactr.excalidraw.render import describe
from artifactr.excalidraw.retention import thin_revisions
from artifactr.excalidraw.sweep import SWEEPER, sweep_tombstones
from artifactr.excalidraw.tools import diagram_tools
from artifactr.excalidraw.types import (
    EXCALIDRAW_TYPES,
    Diagram,
    DiagramComment,
    DiagramFile,
    Element,
    Scene,
)

__all__ = [
    "EXCALIDRAW",
    "EXCALIDRAW_TYPES",
    "SWEEPER",
    "ConversionFailed",
    "Converted",
    "Converter",
    "Diagram",
    "DiagramComment",
    "DiagramFile",
    "Element",
    "FakeConverter",
    "Scene",
    "WorkerConverter",
    "describe",
    "diagram_tools",
    "element_patch",
    "excalidraw_checks",
    "excalidraw_key_of",
    "rebase",
    "reconcile",
    "sweep_tombstones",
    "thin_revisions",
]
