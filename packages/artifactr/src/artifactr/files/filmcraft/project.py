"""What the adapter reads from a video project itself: its format, and what it draws from outside.

A `.fcproj` is JSON that says it is one by its `format`. Its items are of the kinds a project
holds itself, sequences, graphics and media, and anything else is refused. Its media are its own
when FilmCraft generates them (bars, mattes, demo footage); an imported file, a proxy, or a LUT
from a file or the user's library is named by path, outside the project, so a project that holds
one isn't a whole file: its frames would depend on files lattice doesn't keep (native files
ADR-0016). Of FilmCraft 0.8.0's 303 effects, only its colour effect's two LUTs take a path, as
its `effects.list` says of their parameters' types.
"""

from collections.abc import Iterator
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

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
    audio_tracks: list[_Track] = []


class _Media(BaseModel):
    """A medium's two fields that FilmCraft reads a file for: its source and its proxy.

    Its other fields, its info and how it is interpreted, FilmCraft reads from the project
    itself, so they are left as they are.
    """

    media: dict[str, JsonValue]
    """Where its frames come from: `Generator`, FilmCraft's own, or a file, by path."""

    proxy: JsonValue = None


class _Kind(BaseModel):
    """What an item is: one of the kinds a project holds itself, and anything else is extra."""

    model_config = ConfigDict(extra="allow")

    media: _Media | None = Field(default=None, alias="Media")
    sequence: _Sequence | None = Field(default=None, alias="Sequence")
    graphic: JsonValue = Field(default=None, alias="Graphic")


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
    """What an item draws from outside, by name.

    The item itself, if it is of a kind no project holds itself, or a medium that isn't
    FilmCraft's generator's; and each LUT one of its clips names.
    """
    if item.kind.model_extra or (
        (media := item.kind.media) and (set(media.media) != {"Generator"} or media.proxy)
    ):
        yield item.name
    sequence = item.kind.sequence
    for track in [*sequence.video_tracks, *sequence.audio_tracks] if sequence else []:
        for clip in track.items:
            for effect in clip.effects:
                for lut in LUTS:
                    named = effect.params[lut].value.get("Text") if lut in effect.params else ""
                    if named and not str(named).startswith("builtin:"):
                        yield f"{clip.name}'s LUT {named}"
