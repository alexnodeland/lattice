"""JSON Schema helpers for Pydantic models.

A member of a discriminated union, such as a command, gives its tag (``type`` or ``kind``) a
default, so Python code can leave it out. A client can't: the discriminator needs the tag to tell
the members apart. Pydantic's schema calls a field with a default optional, so each member's
config names :func:`tag_required`, which says what the discriminator does.
"""

from typing import cast

from pydantic import JsonValue

__all__ = ["tag_required"]


def tag_required(schema: dict[str, JsonValue]) -> None:
    """Mark a model's fields fixed to one value, its tags, required in its JSON Schema.

    Name it as a model's ``json_schema_extra``.
    """
    properties = cast("dict[str, dict[str, JsonValue]]", schema.get("properties", {}))
    required = cast("list[JsonValue]", schema.setdefault("required", []))
    required += [
        name for name, field in properties.items() if "const" in field and name not in required
    ]
