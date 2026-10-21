"""What the adapter reads from an audio session itself: its format, and what it draws from outside.

A `.scraft` is JSON that says its `format_version` and holds its tracks. MIDI and SoundCraft's
built-in instruments and effects are held in the session itself. Its audio, recorded, imported
or loaded into its sampler, and its video are its `sources` and `videos`, files a save writes
beside the session; and a plugin of another maker's, a VST3, CLAP or Audio Unit, named by its
format and id, is code installed on the machine that SoundCraft would load. A session with any
isn't a whole file (native files ADR-0016).
"""

from collections.abc import Iterator
from typing import Final

from pydantic import BaseModel, JsonValue, ValidationError

from artifactr.files.app import AppFailed
from artifactr.files.craft.project import project
from artifactr.files.manifest import SCRAFT

PLUGINS: Final = ("vst3:", "clap:", "au:")
"""How SoundCraft names a plugin of another maker's: its format, then its id."""

NAMED: Final = frozenset({"plugin", "instrument"})
"""The fields that name a plugin: a session's and a command's (`track.new`'s `instrument`)."""


class _Medium(BaseModel):
    name: str = ""


class _File(BaseModel):
    sources: list[_Medium] = []
    videos: list[_Medium] = []


def media_type(content: bytes) -> str | None:
    """`SCRAFT` if the bytes are a JSON object that says its version and holds tracks, else None."""
    found = project(content)
    if found is None or not isinstance(found.get("format_version"), int):
        return None
    return SCRAFT if isinstance(found.get("tracks"), list) else None


def outside(content: bytes) -> list[str]:
    """What a `.scraft` draws from outside it, by name: none for a whole session.

    Its audio and video by name, and each plugin of another maker's by its id, such as
    `vst3:…`, `PLUGINS`: SoundCraft names its own with no format, such as `compressor`.
    Call it once `media_type` has said the bytes are a `.scraft`.

    Raises:
        AppFailed: `refused` if its sources aren't a session's.
    """
    session = project(content)
    try:
        found = _File.model_validate(session)
    except ValidationError:
        raise AppFailed("refused", "not a .scraft: its sources aren't a session's") from None
    media = [medium.name for medium in (*found.sources, *found.videos)]
    return [*media, *sorted(set(plugins(session)))]


def plugins(node: JsonValue) -> Iterator[str]:
    """Every plugin of another maker's that JSON names, by its id, however it is cased.

    A plugin is named by a `plugin` or an `instrument` field; the JSON is walked without recursion.
    """
    stack: list[JsonValue] = [node]
    while stack:
        found = stack.pop()
        if isinstance(found, dict):
            for key, value in found.items():
                if key in NAMED and isinstance(value, str) and value.casefold().startswith(PLUGINS):
                    yield value
                stack.append(value)
        elif isinstance(found, list):
            stack.extend(found)
