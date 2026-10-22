"""A diagram's artifact type, ``excalidraw_diagram`` (lattice RFC-0006, O1).

A diagram is an ordinary JSON artifact: its elements keyed by their own ids, as Excalidraw writes
them, the images it shows by their digests, and what every viewer shares of its scene. Register
:data:`EXCALIDRAW_TYPES` with the application's own types, in ``Workspaces(types=...)``.

- **Permissive by design.** Only an element's ``id``, ``type``, ``version``, ``versionNonce``,
  ``isDeleted``, ``index`` and ``updated`` are validated; every other field is kept as written,
  so a newer Excalidraw's fields survive, and its client migrates them on load.
- **A key is its element's id**, and an image's key is its digest.
- **Limits** hold every revision small, since each stores its whole data and relayr bridges it:
  :data:`MAX_ELEMENTS` and :data:`MAX_DIAGRAM_BYTES`, as RFC-0006's phase 0 measured them. A
  commit's cost grows with the whole scene, about 40 ms in memory and 90 ms on SQLite at the
  limits, for a revision of about 1.2 MB.
"""

import json
from typing import Annotated, ClassVar, Final, Self, override

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, model_validator

from artifactr.core import Artifact, WritePolicy
from artifactr.excalidraw.integrations import DIAGRAM_KIND
from artifactr.excalidraw.render import describe

__all__ = [
    "EXCALIDRAW_TYPES",
    "MAX_DIAGRAM_BYTES",
    "MAX_ELEMENTS",
    "MAX_NAME",
    "MAX_NONCE",
    "MAX_VERSION",
    "Diagram",
    "DiagramFile",
    "Element",
    "ElementId",
    "Scene",
]

MAX_ELEMENTS: Final = 2_000
"""The most elements a diagram holds, tombstones included. RFC-0006's phase 0 measured a commit
at 5,000 at 200 to 400 ms, too slow for its cadence."""

MAX_DIAGRAM_BYTES: Final = 1024 * 1024
"""The largest diagram, in the UTF-8 bytes of its compact JSON, as RFC-0006's phase 0 set it."""

MAX_NAME: Final = 200
"""The longest name of a diagram, in characters."""

MAX_VERSION: Final = 2**53 - 1
"""The largest version, or time, an element holds: the largest integer JavaScript holds exactly."""

MAX_NONCE: Final = 2**31 - 1
"""The largest nonce Excalidraw makes: a random 31-bit integer."""

ElementId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
"""An element's id, as Excalidraw makes them."""

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
"""A SHA-256 digest, as 64 lowercase hexadecimal digits."""


class Element(BaseModel):
    """One Excalidraw element, as 0.18.1 writes it; its other fields are kept as written."""

    model_config = ConfigDict(
        extra="allow", frozen=True, validate_by_name=True, serialize_by_alias=True
    )

    id: ElementId
    type: str = Field(min_length=1)
    """Any type: a newer one is kept, not refused."""

    version: StrictInt = Field(ge=1, le=MAX_VERSION)
    """Grows with every change; Excalidraw's reconciliation depends on it."""

    version_nonce: StrictInt = Field(alias="versionNonce", ge=0, le=MAX_NONCE)
    """Breaks a tie between two elements of one version: the lower wins."""

    is_deleted: bool = Field(default=False, alias="isDeleted")
    """A tombstone, kept so a client mid-edit doesn't bring the element back."""
    index: str | None = None
    """Its fractional index, which orders it; never sort-validated."""

    updated: StrictInt | None = Field(default=None, ge=0, le=MAX_VERSION)

    @model_validator(mode="after")
    def _storable(self) -> Self:
        try:
            json.dumps(self.model_extra, allow_nan=False)
        except ValueError:
            msg = f"element {self.id} holds a number JSON can't: NaN or an infinity"
            raise ValueError(msg) from None
        except RecursionError:
            msg = f"element {self.id} nests too deep to store"
            raise ValueError(msg) from None
        return self


class DiagramFile(BaseModel):
    """An image a diagram shows: bytes in the blob store, named by their digest.

    The shape of artifactr.files' ``Blob``, so that its blob store keeps them once images land.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: Sha256
    size: int = Field(ge=0)
    media_type: str = Field(min_length=1)


class Scene(BaseModel):
    """What every viewer of a diagram shares; zoom, scroll and tool are each viewer's own."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    view_background_color: str = Field(default="#ffffff", max_length=64)
    grid_size: int | None = Field(default=None, ge=1, le=1000)


class Diagram(Artifact, name=DIAGRAM_KIND):
    """An Excalidraw diagram that people and agents draw on together.

    Agents propose changes to it by default: an application that keeps scratch diagrams may
    register a subclass that applies them. People's edits always commit directly.
    """

    write_policy: ClassVar[WritePolicy] = "propose"

    name: str = Field(max_length=MAX_NAME)
    elements: dict[str, Element] = Field(default_factory=dict[str, Element])
    """Keyed by the element's own id."""

    files: dict[str, DiagramFile] = Field(default_factory=dict[str, DiagramFile])
    """Keyed by the image's digest, which is its ``fileId``."""

    scene: Scene = Scene()

    @model_validator(mode="after")
    def _keyed_and_small(self) -> Self:
        for key, element in self.elements.items():
            if key != element.id:
                msg = f"element {element.id} is kept under {key}: an element's key is its id"
                raise ValueError(msg)
        for key, file in self.files.items():
            if key != file.sha256:
                msg = f"image {file.sha256} is kept under {key}: an image's key is its digest"
                raise ValueError(msg)
        if len(self.elements) > MAX_ELEMENTS:
            msg = f"a diagram holds at most {MAX_ELEMENTS} elements, deleted ones included"
            raise ValueError(msg)
        if _size(self.model_dump(mode="json")) > MAX_DIAGRAM_BYTES:
            msg = f"a diagram is at most {MAX_DIAGRAM_BYTES} bytes of JSON"
            raise ValueError(msg)
        return self

    @override
    def render_for_agent(self) -> str:
        """Describe the diagram's live elements in a few lines, never its JSON."""
        elements = {key: e.model_dump(mode="json") for key, e in self.elements.items()}
        return describe(self.name, elements)


def _size(data: JsonValue) -> int:
    return len(json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode())


EXCALIDRAW_TYPES: Final[tuple[type[Artifact], ...]] = (Diagram,)
"""The types to register: ``Workspaces(types=(*mine, *EXCALIDRAW_TYPES))``."""
