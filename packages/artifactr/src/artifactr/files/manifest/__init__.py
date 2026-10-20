"""Native files as artifacts: the manifest types, and the revision that tests its base.

An artifact of a native type is a small Pydantic manifest. It names the file's bytes, by their
SHA-256, in a [`Blobs`][artifactr.files.blobs.Blobs] store, and a revision is ordinary JSON Patch
that first tests the digest it was made from ([`revise`][artifactr.files.manifest.revise]).
"""

from artifactr.files.manifest.revisions import REVISED, revise
from artifactr.files.manifest.types import (
    DOCX,
    DWG,
    DXF,
    IDML,
    OUTLINE_LIMIT,
    PDF,
    PPTX,
    PSD,
    SVG,
    XLSX,
    Blob,
    NativeFile,
    PdfDocument,
    Presentation,
    Provenance,
    Sha256,
    Source,
    WordDocument,
    Workbook,
)

__all__ = [
    "DOCX",
    "DWG",
    "DXF",
    "IDML",
    "OUTLINE_LIMIT",
    "PDF",
    "PPTX",
    "PSD",
    "REVISED",
    "SVG",
    "XLSX",
    "Blob",
    "NativeFile",
    "PdfDocument",
    "Presentation",
    "Provenance",
    "Sha256",
    "Source",
    "WordDocument",
    "Workbook",
    "revise",
]
