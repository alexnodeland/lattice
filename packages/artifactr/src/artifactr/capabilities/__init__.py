"""artifactr's capabilities: its artifact tools, and its catalog, offered through lattice-core.

:class:`ArtifactrProvider` offers the tools every artifact-aware agent has as ``command``
capabilities, to callers outside artifactr's own threads, each called through lattice-core's
enforcement path (lattice RFC-0011, artifactr ADR-0099). :class:`ArtifactrCatalogProvider`
offers every command of artifactr's catalog a client may call, bound to the application's
workspaces and runner (lattice RFC-0014, artifactr ADR-0103). A registry holds one of them,
since they share six names.
"""

from artifactr.capabilities.catalog import FILES, ArtifactrCatalogProvider, CommandRejected
from artifactr.capabilities.provider import (
    NAMES,
    VERSION,
    ActorFor,
    ArtifactrProvider,
    actor_for,
)

__all__ = [
    "FILES",
    "NAMES",
    "VERSION",
    "ActorFor",
    "ArtifactrCatalogProvider",
    "ArtifactrProvider",
    "CommandRejected",
    "actor_for",
]
