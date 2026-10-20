"""What the adapter reads from a Photoshop document itself: its format, told by its header.

A `.psd` and a `.psb`, its large-document form, share a signature and differ by their version.
PhotoCraft saves in the format of the name it is given, so the adapter opens only a `.psd`, and a
save keeps it one: a `.psb` saved as a `.psd` would be converted.
"""

from typing import Final

from artifactr.files.manifest import PSD

SIGNATURE: Final = b"8BPS"
"""Every Photoshop document's first four bytes."""

VERSIONS: Final = {b"\x00\x01": "psd", b"\x00\x02": "psb"}
"""The version after the signature, and the form it says the document is."""


def form(content: bytes) -> str | None:
    """Whether the bytes are a `psd` or a `psb`, by their header, or None if neither."""
    if not content.startswith(SIGNATURE):
        return None
    return VERSIONS.get(content[4:6])


def media_type(content: bytes) -> str | None:
    """The format the bytes are, a `.psd`'s, or None if they are another, a `.psb` too."""
    return PSD if form(content) == "psd" else None
