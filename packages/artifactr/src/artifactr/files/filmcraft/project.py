"""What the adapter reads from a video project itself: its format, and what it draws from outside.

A `.fcproj` is JSON that says it is one by its `format`. Its media are its own when FilmCraft
generates them (bars, mattes, demo footage); an imported file, a proxy, or a LUT from a file or
the user's library is named by path, outside the project, so a project that holds one isn't a
whole file: its frames would depend on files lattice doesn't keep (native files ADR-0016).
"""

from collections.abc import Iterator
from typing import Final

from pydantic import BaseModel, Field, JsonValue, ValidationError

from artifactr.files.app import AppFailed
from artifactr.files.craft.project import project
from artifactr.files.manifest import FCPROJ

FORMAT: Final = "filmcraft.project"
"""What a `.fcproj` says it is, as its `format`."""

LUTS: Final = ("input_lut", "look_lut")
"""The parameters by which a colour effect names a LUT: one of FilmCraft's own is `builtin:`."""


class _Param(BaseModel):
    value: dict[str, JsonValue] = {}


class _Effect(BaseModel):
    params: dict[str, _Param] = {}


class _Clip(BaseModel):
    name: str = ""
    effects: list[_Effect] = []


class _Track(BaseModel):
    items: list[_Clip] = []


class _Sequence(BaseModel):
    video_tracks: list[_Track] = []


class _Media(BaseModel):
    media: dict[str, JsonValue]
    """Where its frames come from: `Generator`, FilmCraft's own, or a file, by path."""

    proxy: JsonValue = None


class _Kind(BaseModel):
    media: _Media | None = Field(default=None, alias="Media")
    sequence: _Sequence | None = Field(default=None, alias="Sequence")


class _Item(BaseModel):
    name: str = ""
    kind: _Kind


class _Project(BaseModel):
    items: dict[str, _Item]


class _File(BaseModel):
    project: _Project


def media_type(content: bytes) -> str | None:
    """`FCPROJ` if the bytes are a JSON object that says it is a `.fcproj`, else None."""
    found = project(content)
    return FCPROJ if found is not None and found.get("format") == FORMAT else None


def outside(content: bytes) -> list[str]:
    """What a `.fcproj` draws from outside it, by name: none for a whole project.

    Call it once `media_type` has said the bytes are a `.fcproj`.

    Raises:
        AppFailed: `refused` if its items aren't a project's.
    """
    try:
        items = _File.model_validate(project(content)).project.items.values()
    except ValidationError:
        raise AppFailed("refused", "not a .fcproj: its items aren't a project's") from None
    return [name for item in items for name in _outside(item)]


def _outside(item: _Item) -> Iterator[str]:
    if (media := item.kind.media) and (set(media.media) != {"Generator"} or media.proxy):
        yield item.name
    for track in item.kind.sequence.video_tracks if item.kind.sequence else []:
        for clip in track.items:
            for effect in clip.effects:
                for lut in LUTS:
                    named = effect.params[lut].value.get("Text") if lut in effect.params else ""
                    if named and not str(named).startswith("builtin:"):
                        yield f"{clip.name}'s LUT {named}"
