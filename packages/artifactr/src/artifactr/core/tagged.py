"""Tagged union members: their tag is required in their JSON Schema.

A member of a discriminated union, such as a command, gives its tag (``type`` or ``kind``) a
default, so Python code can leave it out. A client can't: the discriminator needs the tag to
tell the members apart. Pydantic's schema calls a field with a default optional, so each
member's config names :func:`tag_required`, which says what the discriminator does (artifactr
ADR-0063, reflexr ADR-0061). lattice-core holds it for artifactr and reflexr alike, and this
module re-exports it (lattice ADR-0018).
"""

from lattice_core.schema import tag_required

__all__ = ["tag_required"]
