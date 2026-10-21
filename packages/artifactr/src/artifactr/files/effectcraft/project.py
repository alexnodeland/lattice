"""What the adapter reads from a motion graphics project itself: its format, and its footage.

An `.ecproj` is JSON that says which release saved it, `savedBy`, and its `schema`, and holds its
items: compositions, solids and folders, which are its own, and footage, an image, video, audio
or 3D model named by path, outside the project. A project with footage isn't a whole file: its
frames would depend on files lattice doesn't keep (native files ADR-0016).
"""

from typing import Final

from pydantic import BaseModel, ValidationError

from artifactr.files.app import AppFailed
from artifactr.files.craft.project import project
from artifactr.files.manifest import ECPROJ

OWN: Final = frozenset({"Comp", "Solid", "Folder"})
"""The kinds of item a project holds itself: every other kind is footage, at a path."""


class _Kind(BaseModel):
    type: str


class _Item(BaseModel):
    name: str = ""
    kind: _Kind


class _File(BaseModel):
    items: dict[str, _Item]


def media_type(content: bytes) -> str | None:
    """`ECPROJ` if the bytes are a JSON object that says which release saved it, else None."""
    found = project(content)
    if found is None or not isinstance(found.get("savedBy"), str):
        return None
    return ECPROJ if isinstance(found.get("schema"), int) else None


def outside(content: bytes) -> list[str]:
    """The footage an `.ecproj` draws from outside it, by name: none for a whole project.

    Call it once `media_type` has said the bytes are an `.ecproj`.

    Raises:
        AppFailed: `refused` if its items aren't a project's.
    """
    try:
        items = _File.model_validate(project(content)).items.values()
    except ValidationError:
        raise AppFailed("refused", "not an .ecproj: its items aren't a project's") from None
    return [item.name for item in items if item.kind.type not in OWN]
