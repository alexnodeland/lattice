"""Whether diagrams are on in a workspace, on lattice's shared port (lattice RFC-0006, ADR-0027).

Diagrams are lattice's integration ``excalidraw``, declared in lattice-core's
:data:`~lattice_core.integrations.KNOWN`, off by default. An application gates them with
artifactr's gate: give ``Workspaces(gate=integration_gate(integrations, excalidraw_key_of))``,
and making or changing a diagram while the integration is off is refused as ``not_enabled``.
Diagrams already made stay readable.
"""

from collections.abc import Mapping
from typing import Final, Literal

from pydantic import JsonValue

__all__ = ["DIAGRAM_KIND", "EXCALIDRAW", "IntegrationKey", "excalidraw_key_of"]

EXCALIDRAW: Final = "excalidraw"
"""The integration that governs diagrams."""

DIAGRAM_KIND: Final = "excalidraw_diagram"
"""A diagram's artifact kind."""

IntegrationKey = Literal["excalidraw"]
"""The key a ``not_enabled`` refusal of a diagram names."""


def excalidraw_key_of(kind: str, _data: Mapping[str, JsonValue]) -> str | None:
    """The integration that governs an artifact, for artifactr's ``integration_gate``."""
    return EXCALIDRAW if kind == DIAGRAM_KIND else None
