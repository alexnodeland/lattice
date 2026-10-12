"""Tagged union members: their tag is required in their JSON Schema.

A member of a discriminated union, such as a command, gives its tag (``type`` or ``kind``) a
default, so Python code can leave it out. A client can't: the discriminator needs the tag to
tell the members apart. Pydantic's schema calls a field with a default optional, so each
member's config names :func:`tag_required`, which says what the discriminator does (artifactr
ADR-0063, reflexr ADR-0061).
"""

from typing import cast

from pydantic import JsonValue


# Shared verbatim with reflexr's src/reflexr/core/tagged.py; change both.
def tag_required(schema: dict[str, JsonValue]) -> None:
    """Mark a model's fields fixed to one value, its tags, required in its JSON Schema."""
    properties = cast("dict[str, dict[str, JsonValue]]", schema.get("properties", {}))
    required = cast("list[JsonValue]", schema.setdefault("required", []))
    required += [
        name for name, field in properties.items() if "const" in field and name not in required
    ]
