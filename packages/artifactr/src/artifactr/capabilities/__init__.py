"""artifactr's capabilities: its artifact tools, offered through lattice-core's registry.

:class:`ArtifactrProvider` offers the tools every artifact-aware agent has as ``command``
capabilities, to callers outside artifactr's own threads, each called through lattice-core's
enforcement path (lattice RFC-0011, artifactr ADR-0099).
"""

from artifactr.capabilities.provider import (
    NAMES,
    VERSION,
    ActorFor,
    ArtifactrProvider,
    actor_for,
)

__all__ = ["NAMES", "VERSION", "ActorFor", "ArtifactrProvider", "actor_for"]
