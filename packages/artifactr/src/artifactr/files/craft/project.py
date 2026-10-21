"""What an adapter reads from a project its app keeps as JSON: the project, bounded.

FilmCraft's, EffectCraft's and SoundCraft's projects are JSON documents that name the media
they draw by path. Their adapters read a project before its CLI starts, for its format and for
whether it holds every source it draws (native files ADR-0016), so a stranger's project is read
only within bounds: past `LIMIT` it is too large, and nested past the depth pydantic's parser
reads, or anything but a JSON object, it is no project.
"""

from typing import Final

from pydantic import JsonValue, TypeAdapter, ValidationError

from artifactr.files.app import AppFailed

LIMIT: Final = 16 << 20
"""The most bytes a project may hold: it holds no media, so a larger one is refused unread."""

_JSON: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


def project(content: bytes) -> dict[str, JsonValue] | None:
    """The bytes as a JSON object, or None if they are another JSON value, or not JSON.

    Raises:
        AppFailed: `too_large` past `LIMIT`, before they are read.
    """
    if len(content) > LIMIT:
        raise AppFailed("too_large", f"a project of more than {LIMIT} bytes holds media")
    try:
        found = _JSON.validate_json(content)
    except ValidationError:
        # Not UTF-8, not JSON, or nested deeper than the parser goes.
        return None
    return found if isinstance(found, dict) else None
