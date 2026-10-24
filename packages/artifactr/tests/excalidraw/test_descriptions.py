"""The shared fixture of diagram descriptions, which portalr's port is held to, as `describe`
writes it today."""

import json
from pathlib import Path

from tests.excalidraw.descriptions import fixture

FIXTURE = Path(__file__).parents[2] / "schemas" / "excalidraw_descriptions.json"


def test_the_fixture_is_what_describe_writes() -> None:
    # Regenerate it as descriptions.py says.
    assert json.loads(FIXTURE.read_text()) == fixture()
