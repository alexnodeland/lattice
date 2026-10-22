"""Elements and diagrams the tests draw with."""

from typing import Any

from artifactr.excalidraw import Diagram, Element


def element(key: str, version: int = 1, nonce: int = 10, **fields: Any) -> Element:
    """A rectangle, unless told otherwise, at the origin."""
    data: dict[str, Any] = {
        "id": key,
        "type": "rectangle",
        "version": version,
        "versionNonce": nonce,
        "x": 0,
        "y": 0,
        "width": 10,
        "height": 10,
        **fields,
    }
    return Element.model_validate(data)


def diagram(*elements: Element, name: str = "Plan") -> Diagram:
    return Diagram(name=name, elements={e.id: e for e in elements})


def moved(before: Element, x: float, nonce: int = 20) -> Element:
    """The element moved, at one version above."""
    return before.model_copy(update={"version": before.version + 1, "version_nonce": nonce, "x": x})


def data(*elements: Element, name: str = "Plan") -> dict[str, Any]:
    return diagram(*elements, name=name).to_json()
