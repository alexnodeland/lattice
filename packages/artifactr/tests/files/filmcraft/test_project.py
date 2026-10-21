"""Whether bytes are a `.fcproj`, told from its JSON, and what one draws from outside it."""

import json

import pytest

from artifactr.files.app import AppFailed
from artifactr.files.craft.project import LIMIT
from artifactr.files.filmcraft import media_type, outside
from artifactr.files.manifest import FCPROJ


def fcproj(**items: object) -> bytes:
    return json.dumps({"format": "filmcraft.project", "project": {"items": items}}).encode()


def media(name: str, media: object, **fields: object) -> dict[str, object]:
    return {"name": name, "kind": {"Media": {"media": media, **fields}}}


def graded(look: object) -> dict[str, object]:
    """A sequence whose one clip has a colour effect with a LUT, and a blur with none."""
    params = {"input_lut": {"value": {"Text": ""}}, "look_lut": {"value": look}}
    effects = [{"effect": "lumetri", "params": params}, {"effect": "gaussian_blur"}]
    clip = {"name": "Shot", "effects": effects}
    return {"name": "Main", "kind": {"Sequence": {"video_tracks": [{"items": [clip]}]}}}


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (fcproj(), FCPROJ),
        (b' { "project": {}, "format" : "filmcraft.project" }', FCPROJ),
        (b'{"format": "filmcraft.template"}', None),
        (b'["filmcraft.project"]', None),
        (b'{"format": "filmcraft.project"', None),
        (b"\xff\xfe", None),
        (b"", None),
    ],
)
def test_a_fcproj_is_told_by_its_format(content: bytes, expected: str | None) -> None:
    assert media_type(content) == expected


def test_a_project_larger_than_any_without_media_is_too_large() -> None:
    with pytest.raises(AppFailed, match="holds media") as refused:
        media_type(b" " * (LIMIT + 1))
    assert refused.value.failure == "too_large"


def test_a_project_of_filmcrafts_own_media_draws_nothing_from_outside() -> None:
    generated = media("Bars", {"Generator": "BarsAndTone"}, proxy=None)
    graphic = {"name": "Graphic", "kind": {"Graphic": {"width": 64}}}
    assert outside(fcproj(**{"1": generated, "2": graphic, "3": graded({"Text": ""})})) == []
    assert outside(fcproj(**{"4": graded({"Text": "builtin:look-teal-orange"})})) == []


@pytest.mark.parametrize(
    ("item", "named"),
    [
        (media("a.mov", {"File": {"path": "/media/a.mov"}}), "a.mov"),
        (media("Bars", {"Generator": "BarsAndTone"}, proxy={"path": "b.mov"}), "Bars"),
        (media("Both", {"Generator": "BlackVideo", "File": {"path": "c.mov"}}), "Both"),
        (graded({"Text": "/luts/film.cube"}), "Shot's LUT /luts/film.cube"),
        (graded({"Text": "lib:1"}), "Shot's LUT lib:1"),
    ],
)
def test_media_and_luts_at_a_path_are_drawn_from_outside(item: object, named: str) -> None:
    assert outside(fcproj(**{"1": item})) == [named]


def test_a_project_whose_items_arent_a_projects_is_refused() -> None:
    with pytest.raises(AppFailed, match="its items aren't a project's") as refused:
        outside(b'{"format": "filmcraft.project", "project": {"items": ["a.mov"]}}')
    assert refused.value.failure == "refused"
