"""A diagram's type: permissive about Excalidraw's fields, strict about keys and size."""

import pytest
from pydantic import ValidationError

from artifactr.core import load_artifact
from artifactr.excalidraw import Diagram, excalidraw_key_of
from artifactr.excalidraw.types import MAX_DIAGRAM_BYTES, MAX_ELEMENTS
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
    many = {f"e{i}": element(f"e{i}") for i in range(MAX_ELEMENTS + 1)}
    with pytest.raises(ValidationError, match=f"at most {MAX_ELEMENTS} elements"):
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
