"""Manifests for the tests: a Word document's, with made-up digests."""

import hashlib

from artifactr_files.manifest import DOCX, Blob, Provenance, WordDocument


def digest(seed: str) -> str:
    """A made-up SHA-256."""
    return hashlib.sha256(seed.encode()).hexdigest()


def blob(seed: str, media_type: str = DOCX) -> Blob:
    """A blob named by a made-up digest."""
    return Blob(sha256=digest(seed), size=len(seed), media_type=media_type)


def document(seed: str, *, name: str = "contract.docx", outline: str = "") -> WordDocument:
    """A Word document whose content and fingerprint come from `seed`."""
    return WordDocument(
        name=name,
        content=blob(seed),
        fingerprint=digest(f"fingerprint {seed}"),
        text=blob(f"text {seed}", "text/plain; charset=utf-8"),
        review=blob(f"review {seed}", "application/json"),
        outline=outline,
        provenance=Provenance(source="upload"),
    )
