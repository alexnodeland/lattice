"""The manifest types: what a native file's artifact holds, and what the agent sees of it."""

import pytest
from pydantic import ValidationError

from artifactr.core import NotFound, get_artifact_type
from artifactr.files.manifest import (
    DOCX,
    OUTLINE_LIMIT,
    PPTX,
    XLSX,
    Presentation,
    Provenance,
    WordDocument,
    Workbook,
)
from tests.files.files_of import blob, digest, document


def test_a_word_document_is_registered_and_proposed_by_agents() -> None:
    assert get_artifact_type("word_document") is WordDocument
    assert WordDocument.formats == frozenset({DOCX})
    assert WordDocument.write_policy == "propose"
    with pytest.raises(NotFound):
        get_artifact_type("native_file")  # abstract: never registered


def test_each_crafting_apps_type_is_registered_with_its_format() -> None:
    assert get_artifact_type("workbook") is Workbook
    assert Workbook.formats == frozenset({XLSX})
    assert get_artifact_type("presentation") is Presentation
    assert Presentation.formats == frozenset({PPTX})


def test_its_content_is_in_its_format() -> None:
    with pytest.raises(ValidationError, match="holds"):
        WordDocument(
            name="notes.txt",
            content=blob("notes", "text/plain"),
            fingerprint=digest("notes"),
            provenance=Provenance(source="upload"),
        )


@pytest.mark.parametrize("sha256", ["", "A" * 64, "a" * 63, "g" * 64])
def test_a_digest_is_sha256_in_lowercase_hex(sha256: str) -> None:
    with pytest.raises(ValidationError):
        WordDocument.model_validate({**document("x").to_json(), "fingerprint": sha256})


def test_an_outline_is_bounded() -> None:
    data = document("x").to_json()
    WordDocument.model_validate({**data, "outline": "o" * OUTLINE_LIMIT})
    with pytest.raises(ValidationError):
        WordDocument.model_validate({**data, "outline": "o" * (OUTLINE_LIMIT + 1)})


@pytest.mark.parametrize(
    ("pages", "outline", "seen"),
    [
        (None, "", "contract.docx"),
        (1, "", "contract.docx (1 page)"),
        (3, "Terms\nPayment", "contract.docx (3 pages)\n\nTerms\nPayment"),
        (None, "Terms", "contract.docx\n\nTerms"),
    ],
)
def test_the_agent_sees_its_name_pages_and_outline(
    pages: int | None, outline: str, seen: str
) -> None:
    manifest = document("x").model_copy(update={"pages": pages, "outline": outline})
    assert manifest.render_for_agent() == seen
    assert digest("x") not in manifest.render_for_agent(), "never a digest"
