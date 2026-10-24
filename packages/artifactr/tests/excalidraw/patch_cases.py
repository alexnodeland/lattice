"""The shared fixture of diagram patches: what `element_patch` writes for each case, which
portalr's canvas's port of it is held to (portalr ADR-0074).

The fixture is checked in at ``schemas/excalidraw_patches.json``; ``test_patch_cases`` fails if it
drifts. Regenerate it with:

    uv run python -m tests.excalidraw.patch_cases > schemas/excalidraw_patches.json
"""

import json
import sys
from typing import Any

from artifactr.excalidraw import Diagram, DiagramFile, Element, element_patch, rebase


def _element(key: str, version: int = 1, nonce: int = 10, **fields: Any) -> dict[str, Any]:
    return {
        "id": key,
        "type": "rectangle",
        "version": version,
        "versionNonce": nonce,
        "isDeleted": False,
        "x": 0,
        "y": 0,
        "width": 10,
        "height": 10,
        **fields,
    }


IMAGE = {"sha256": "a" * 64, "size": 68, "media_type": "image/png"}

BASE = {
    "name": "Plan",
    "elements": {
        "r1": _element("r1"),
        "r2": _element("r2", x=100),
        "gone": _element("gone", 3, isDeleted=True),
        "t1": _element("t1", type="text", text="Hi", containerId="r1"),
    },
    "files": {},
}

CASES: list[dict[str, Any]] = [
    {"case": "nothing changed", "elements": BASE["elements"], "files": {}},
    {
        "case": "one moved, one added",
        "elements": {
            **BASE["elements"],
            "r1": _element("r1", 2, 11, x=40),
            "e1": _element("e1", type="ellipse", x=300),
        },
        "files": {},
    },
    {
        "case": "one deleted, its label with it, the rest as they were",
        "elements": {
            **BASE["elements"],
            "r2": _element("r2", 2, 7, x=100, isDeleted=True),
            "t1": _element("t1", 2, 8, type="text", text="Hi", containerId="r1", isDeleted=True),
        },
        "files": {},
    },
    {
        "case": "a label edited, and fields the base left out",
        "elements": {
            **BASE["elements"],
            "t1": _element("t1", 4, 9, type="text", text="Hello", containerId="r1"),
            "r1": {**_element("r1", 2, 3), "index": "a1", "updated": 1792000000000},
        },
        "files": {},
    },
    {
        "case": "an image put on it, its file added",
        "elements": {
            **BASE["elements"],
            "p1": _element("p1", type="image", fileId="a" * 64, status="saved"),
        },
        "files": {"a" * 64: IMAGE},
    },
    {
        "case": "an element the edit leaves out is kept",
        "elements": {"r1": BASE["elements"]["r1"]},
        "files": {},
    },
]


REBASES: list[dict[str, Any]] = [
    {
        "case": "a change the head didn't touch, and a new element, kept as they are",
        "local": {**BASE["elements"], "r1": _element("r1", 2, 11, x=40), "n1": _element("n1")},
        "head": {**BASE["elements"], "r2": _element("r2", 2, 5, x=100)},
    },
    {
        "case": "a change that wins over the head's goes above it, with a new nonce",
        "local": {**BASE["elements"], "r1": _element("r1", 3, 11, x=40)},
        "head": {**BASE["elements"], "r1": _element("r1", 2, 5, x=70)},
    },
    {
        "case": "of one version, the lower nonce wins",
        "local": {**BASE["elements"], "r1": _element("r1", 2, 4, x=40), "r2": _element("r2", 2, 9)},
        "head": {**BASE["elements"], "r1": _element("r1", 2, 5, x=70), "r2": _element("r2", 2, 6)},
    },
    {
        "case": "an element the writer left as it was takes the head's",
        "local": BASE["elements"],
        "head": {**BASE["elements"], "gone": _element("gone", 4, 2, isDeleted=False)},
    },
]
"""Rebases: the writer's elements, made from the base, moved onto a head that moved on. Where a
nonce is drawn anew, the fixture says ``"new"``: it is random."""


def _rebased(case: dict[str, Any]) -> dict[str, Any]:
    base = Diagram.model_validate(BASE)
    local = {key: Element.model_validate(value) for key, value in case["local"].items()}
    head = Diagram.model_validate({**BASE, "elements": case["head"]})
    merged = {}
    for key, element in rebase(base, local, head).items():
        written = element.model_dump(mode="json", by_alias=True)
        nonces = {each.version_nonce for each in (local.get(key), head.elements.get(key)) if each}
        if element.version_nonce not in nonces:
            written["versionNonce"] = "new"
        merged[key] = written
    return {**case, "rebased": merged}


def fixture() -> dict[str, Any]:
    """The base, and each case with the patch `element_patch` writes for it."""
    base = Diagram.model_validate(BASE)
    cases = []
    for case in CASES:
        elements = {key: Element.model_validate(value) for key, value in case["elements"].items()}
        files = {key: DiagramFile.model_validate(value) for key, value in case["files"].items()}
        patch = element_patch(base, elements, files)
        cases.append({**case, "ops": [dict(op) for op in patch.ops]})
    return {
        "base": base.to_json(),
        "cases": cases,
        "rebases": [_rebased(case) for case in REBASES],
    }


if __name__ == "__main__":
    json.dump(fixture(), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
