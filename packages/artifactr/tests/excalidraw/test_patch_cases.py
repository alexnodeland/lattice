"""The shared fixture of diagram patches, which portalr's canvas is held to, as `element_patch`
writes it today."""

import json
from pathlib import Path

from tests.excalidraw.patch_cases import fixture

FIXTURE = Path(__file__).parents[2] / "schemas" / "excalidraw_patches.json"


def test_the_fixture_is_what_element_patch_writes() -> None:
    # Regenerate it as patch_cases.py says.
    assert json.loads(FIXTURE.read_text()) == fixture()
