"""A diagram's type: permissive about Excalidraw's fields, strict about keys and size."""

import json
import math
from typing import Any

import pytest
from pydantic import ValidationError

from artifactr.core import ValidationFailed, load_artifact
from artifactr.excalidraw import Diagram, excalidraw_key_of
from artifactr.excalidraw.types import MAX_DIAGRAM_BYTES, MAX_ELEMENTS, MAX_NONCE, MAX_VERSION
from tests.excalidraw.scenes import data, element


def test_a_diagram_keeps_every_field_it_doesnt_know() -> None:
    written = element("r1", strokeColor="#1e1e1e", boundElements=[{"id": "t1", "type": "text"}])
    newer = element("s1", type="a-shape-from-a-newer-excalidraw", someday=True)
    loaded = load_artifact("excalidraw_diagram", data(written, newer))
    assert isinstance(loaded, Diagram)
    assert loaded.elements["r1"].model_dump(mode="json")["strokeColor"] == "#1e1e1e"
    kept = loaded.elements["s1"].model_dump(mode="json")
    assert (kept["type"], kept["someday"]) == ("a-shape-from-a-newer-excalidraw", True)


def test_excalidraws_names_are_kept_on_the_wire() -> None:
    written = element("r1", isDeleted=True)
    assert written.is_deleted
    assert {"versionNonce", "isDeleted"} <= set(written.model_dump(mode="json"))


def test_an_element_kept_under_another_key_is_refused() -> None:
    with pytest.raises(ValidationError, match="an element's key is its id"):
        Diagram(name="Plan", elements={"r2": element("r1")})


def test_an_image_kept_under_another_key_is_refused() -> None:
    image = {"sha256": "a" * 64, "size": 1, "media_type": "image/png"}
    with pytest.raises(ValidationError, match="an image's key is its digest"):
        Diagram.model_validate({"name": "Plan", "files": {"b" * 64: image}})


def test_an_element_id_is_excalidraws_shape() -> None:
    with pytest.raises(ValidationError):
        element("a/b")


def test_a_diagram_holds_at_most_its_elements() -> None:
    assert (MAX_ELEMENTS, MAX_DIAGRAM_BYTES) == (2_000, 1024 * 1024), "phase 0's limits"
    full = {f"e{i}": element(f"e{i}", isDeleted=i % 2 == 0) for i in range(MAX_ELEMENTS)}
    assert len(Diagram(name="Plan", elements=full).elements) == MAX_ELEMENTS
    many = {f"e{i}": element(f"e{i}") for i in range(MAX_ELEMENTS + 1)}
    with pytest.raises(
        ValidationError, match=f"at most {MAX_ELEMENTS} elements, deleted ones included"
    ):
        Diagram(name="Plan", elements=many)


def test_a_diagram_holds_at_most_its_bytes() -> None:
    heavy = element("t1", type="text", text="x" * MAX_DIAGRAM_BYTES)
    with pytest.raises(ValidationError, match=f"at most {MAX_DIAGRAM_BYTES} bytes"):
        Diagram(name="Plan", elements={"t1": heavy})


def test_agents_propose_by_default() -> None:
    assert Diagram.write_policy == "propose"
    assert Diagram.kind == "excalidraw_diagram"


def test_only_a_diagram_is_the_integrations() -> None:
    assert excalidraw_key_of("excalidraw_diagram", {}) == "excalidraw"
    assert excalidraw_key_of("note", {}) is None


@pytest.mark.parametrize(
    "fields",
    [
        {"version": 10**400},
        {"version": 2**53},
        {"version": True},
        {"version": 2.0},
        {"version": "2"},
        {"nonce": -1},
        {"nonce": 2**31},
        {"nonce": False},
        {"x": math.nan},
        {"x": math.inf},
        {"points": [[0, -math.inf]]},
        {"updated": 1.5},
        {"x": 10**5000},
        {"x": 2**53},
        {"points": [[0, -(2**60)]]},
    ],
)
def test_a_hostile_element_is_refused(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        element("r1", **fields)


def test_an_element_nested_past_what_json_holds_is_refused() -> None:
    deep: dict[str, Any] = {}
    inner = deep
    for _ in range(100_000):
        inner["a"] = {}
        inner = inner["a"]
    with pytest.raises(ValidationError, match="nests too deep"):
        element("r1", deep=deep)


def test_the_largest_version_and_nonce_are_kept() -> None:
    kept = element("r1", version=MAX_VERSION, nonce=MAX_NONCE)
    assert (kept.version, kept.version_nonce) == (MAX_VERSION, MAX_NONCE)


def test_core_refuses_a_huge_integer_as_validation_failed() -> None:
    huge = {"id": "r1", "type": "rectangle", "version": 1, "versionNonce": 1, "x": 10**5000}
    data = {"name": "Plan", "elements": {"r1": huge}}
    with pytest.raises(ValidationFailed, match="invalid excalidraw_diagram data") as refused:
        load_artifact("excalidraw_diagram", data)
    assert "JavaScript can't hold exactly" in json.dumps(refused.value.errors)


@pytest.mark.parametrize(
    "size", [10**5000, 2**53, -1, 1.5, True], ids=["huge", "past-2^53", "negative", "float", "bool"]
)
def test_an_images_size_is_a_whole_number_javascript_holds(size: object) -> None:
    image = {"sha256": "a" * 64, "size": size, "media_type": "image/png"}
    with pytest.raises(ValidationError):
        Diagram.model_validate({"name": "Plan", "files": {"a" * 64: image}})
