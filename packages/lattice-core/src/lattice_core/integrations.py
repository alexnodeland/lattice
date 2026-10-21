"""Integrations: what a workspace offers beyond the libraries' own, each switched on or off.

An integration is named by a key, such as ``tracker:plane`` or ``ui:forms``. Each is declared
once, in a registry, with whether it is on where no one has set it and a sentence that says what
it is: :data:`KNOWN` is lattice's, and an application that adds its own declares one more
:class:`Integration` and passes :func:`registry` both.

Before an integration acts in a workspace, its package asks an :class:`Integrations`. grantr's
adapter answers from the deployment's installation, the tenant's setting and the workspace's
together: it is on only where each of them leaves it on, and a level no one has set inherits
the one above (lattice ADR-0027). Without a store, :class:`Defaults` answers each key's
default.

The port only answers yes or no, so an external provider, such as a feature-flag service, can
only narrow it: an :class:`Integrations` of the application's that asks grantr's first, and
then the provider, is on only where both are. lattice builds none (lattice ADR-0027).
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Protocol

__all__ = ["KEY", "KNOWN", "Defaults", "Integration", "Integrations", "registry"]

KEY: Final = re.compile(r"[a-z][a-z0-9-]*(:[a-z][a-z0-9-]*)?")
"""An integration key's form: a name, or a family, a colon and a name, such as ``files:wordcraft``,
in lowercase letters, digits and hyphens."""


@dataclass(frozen=True)
class Integration:
    """One integration: its key, whether it is on where no one has set it, and what it is.

    Raises:
        ValueError: If the key isn't of :data:`KEY`'s form, or the description is empty.
    """

    key: str
    default: bool
    description: str
    """One sentence, for the admin who switches it."""

    def __post_init__(self) -> None:
        if not KEY.fullmatch(self.key):
            raise ValueError(f"an integration key is a name or family:name, not {self.key!r}")
        if not self.description.strip():
            raise ValueError(f"{self.key} needs a description")


def registry(*integrations: Integration) -> Mapping[str, Integration]:
    """Return the integrations by key, in the order given, read-only.

    Raises:
        ValueError: If two declare one key.
    """
    known: dict[str, Integration] = {}
    for integration in integrations:
        if integration.key in known:
            raise ValueError(f"{integration.key} is declared twice")
        known[integration.key] = integration
    return MappingProxyType(known)


KNOWN: Final = registry(
    Integration(
        "tracker:plane",
        default=True,
        description="Plane: rules file and change work items in a Plane project.",
    ),
    Integration(
        "tracker:vikunja",
        default=True,
        description="Vikunja: rules file and change tasks in a Vikunja project.",
    ),
    Integration(
        "files:wordcraft",
        default=True,
        description="WordCraft: Word documents kept as native files, edited by people and agents.",
    ),
    Integration(
        "files:gridcraft",
        default=False,
        description="GridCraft: Excel workbooks kept as native files, edited by people and agents.",
    ),
    Integration(
        "files:deckcraft",
        default=False,
        description=(
            "DeckCraft: PowerPoint presentations kept as native files, edited by people and agents."
        ),
    ),
    Integration(
        "files:pdfcraft",
        default=False,
        description="PdfCraft: PDF documents kept as native files, edited by people and agents.",
    ),
    Integration(
        "files:cadcraft",
        default=False,
        description=(
            "CADCraft: DXF and DWG drawings kept as native files, edited by people and agents."
        ),
    ),
    Integration(
        "files:photocraft",
        default=False,
        description=(
            "PhotoCraft: Photoshop documents kept as native files, edited by people and agents."
        ),
    ),
    Integration(
        "files:vectorcraft",
        default=False,
        description="VectorCraft: SVG drawings kept as native files, edited by people and agents.",
    ),
    Integration(
        "files:designcraft",
        default=False,
        description=(
            "DesignCraft: InDesign layouts, as IDML, kept as native files, edited by people "
            "and agents."
        ),
    ),
    Integration(
        "files:figcraft",
        default=False,
        description=(
            "FigCraft: interface designs kept as native files, edited by people and agents."
        ),
    ),
    Integration(
        "files:freecad",
        default=False,
        description="FreeCAD: 3D models kept as native files, edited by people and agents.",
    ),
    Integration(
        "files:filmcraft",
        default=False,
        description=(
            "FilmCraft: video projects that hold their own media, kept as native files, edited "
            "by people and agents."
        ),
    ),
    Integration(
        "files:effectcraft",
        default=False,
        description=(
            "EffectCraft: motion graphics projects that hold no footage, kept as native files, "
            "edited by people and agents."
        ),
    ),
    Integration(
        "files:soundcraft",
        default=False,
        description=(
            "SoundCraft: audio sessions of MIDI and its own instruments, kept as native files, "
            "edited by people and agents."
        ),
    ),
    Integration(
        "files:lightcraft",
        default=False,
        description="LightCraft: photos developed and exported, one file at a time.",
    ),
    Integration(
        "ui:forms",
        default=True,
        description="Forms: the agent asks with a form, and people fill it in the chat.",
    ),
    Integration(
        "ui:dashboards",
        default=True,
        description="Dashboards: the agent shows figures and charts as a dashboard in the chat.",
    ),
    Integration(
        "ui:mini-apps",
        default=False,
        description="Mini apps: small apps the agent writes, run apart from the portal.",
    ),
    Integration(
        "excalidraw",
        default=True,
        description="Diagrams: Excalidraw drawings that people and agents draw on together.",
    ),
    Integration(
        "markdown:math",
        default=True,
        description="Math: formulas in messages and documents, typeset.",
    ),
    Integration(
        "markdown:mermaid",
        default=False,
        description="Mermaid: diagrams written as text in messages, drawn.",
    ),
)
"""lattice's integrations, by key: one :class:`Integration` each."""


class Integrations(Protocol):
    """Whether an integration is on in a tenant's workspace: the port its package asks first.

    It is asked before each command, and each model request, of an integration's, so an
    implementation answers from what it reads cheaply. A key it doesn't know is off. Its
    arguments are positional, so an implementation names them as it likes.
    """

    async def is_enabled(self, tenant_id: str, workspace_id: str, key: str, /) -> bool:
        """Return whether the integration ``key`` is on in the tenant's workspace."""
        ...


class Defaults:
    """Each integration's default, everywhere: the answer without a store.

    Args:
        known: The integrations it knows; :data:`KNOWN` if omitted. Any other key is off.
    """

    def __init__(self, known: Mapping[str, Integration] = KNOWN) -> None:
        self._known = known

    async def is_enabled(self, _tenant_id: str, _workspace_id: str, key: str, /) -> bool:
        """Return the integration's default, or False for a key it doesn't know."""
        integration = self._known.get(key)
        return integration is not None and integration.default
