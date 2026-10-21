"""Whether bytes are an `.ecproj`, told from its JSON, and the footage one draws on."""

import json

import pytest

from artifactr.files.app import AppFailed
from artifactr.files.effectcraft import media_type, outside
from artifactr.files.manifest import ECPROJ


def ecproj(**items: object) -> bytes:
    return json.dumps({"savedBy": "0.11.1", "schema": 2, "items": items}).encode()


def item(name: str, kind: str, **fields: object) -> dict[str, object]:
    return {"name": name, "kind": {"type": kind, **fields}}


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (ecproj(), ECPROJ),
        (b'{"schema": 1, "savedBy": "0.9.0"}', ECPROJ),
        (b'{"savedBy": 11, "schema": 2}', None),
        (b'{"savedBy": "0.11.1", "schema": "2"}', None),
        (b'{"schema": 2}', None),
        (b'["savedBy"]', None),
        (b"", None),
    ],
)
def test_an_ecproj_is_told_by_the_release_that_saved_it(
    content: bytes, expected: str | None
) -> None:
    assert media_type(content) == expected


def test_compositions_solids_and_folders_are_a_projects_own() -> None:
    own = ecproj(**{"1": item("Main", "Comp"), "2": item("Red", "Solid"), "3": item("F", "Folder")})
    assert outside(own) == []


@pytest.mark.parametrize("kind", ["Footage", "Model", "Sequence"])
def test_anything_else_is_footage_drawn_from_outside(kind: str) -> None:
    assert outside(ecproj(**{"1": item("shot", kind, path="shot.mov")})) == ["shot"]


def test_a_project_whose_items_arent_a_projects_is_refused() -> None:
    with pytest.raises(AppFailed, match="its items aren't a project's") as refused:
        outside(b'{"savedBy": "0.11.1", "schema": 2, "items": {"1": {"kind": "Comp"}}}')
    assert refused.value.failure == "refused"
