"""The stackr template's image copies nothing hidden from brand/ (lattice security review)."""

from pathlib import Path

DOCKERIGNORE = Path(__file__).parents[1] / "packages/stackr/template/.dockerignore"


def test_the_image_leaves_out_every_hidden_file_of_the_brand_kit() -> None:
    patterns = [line.strip() for line in DOCKERIGNORE.read_text().splitlines()]
    assert "brand/**/.*" in patterns, "a .env beside the kit would go into the image"
    assert ".env" in patterns
