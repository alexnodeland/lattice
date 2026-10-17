"""Native files as artifacts: the manifest types, and the revision that tests its base.

An artifact of a native type is a small Pydantic manifest. It names the file's bytes, by their
SHA-256, in a [`Blobs`][artifactr_files.blobs.Blobs] store, and a revision is ordinary JSON Patch
that first tests the digest it was made from ([`revise`][artifactr_files.manifest.revise]).
"""

from artifactr_files.manifest.revisions import REVISED, revise
from artifactr_files.manifest.types import (
    DOCX,
    OUTLINE_LIMIT,
    Blob,
    NativeFile,
    Provenance,
    Sha256,
    Source,
    WordDocument,
)

__all__ = [
    "DOCX",
    "OUTLINE_LIMIT",
    "REVISED",
    "Blob",
    "NativeFile",
    "Provenance",
    "Sha256",
    "Source",
    "WordDocument",
    "revise",
]
