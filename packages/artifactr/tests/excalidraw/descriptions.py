"""The shared fixture of diagram descriptions: what `describe` writes for each case, which
portalr's port of it is held to (portalr ADR-0072).

The fixture is checked in at ``schemas/excalidraw_descriptions.json``; ``test_descriptions``
fails if it drifts. Regenerate it with:

    uv run python -m tests.excalidraw.descriptions > schemas/excalidraw_descriptions.json
"""

import json
import sys
from typing import Any

from artifactr.excalidraw.render import MAX_DESCRIPTION, describe


def _shape(key: str, kind: str = "rectangle", **fields: Any) -> tuple[str, dict[str, Any]]:
    return key, {"id": key, "type": kind, "x": 0, "y": 0, "width": 100, "height": 50, **fields}


def _label(key: str, container: str, text: str) -> tuple[str, dict[str, Any]]:
    return key, {
        "id": key,
        "type": "text",
        "containerId": container,
        "text": text,
        "x": 10,
        "y": 10,
    }


def _arrow(
    key: str, start: str | None, end: str | None, **fields: Any
) -> tuple[str, dict[str, Any]]:
    bindings = {
        "startBinding": {"elementId": start} if start else None,
        "endBinding": {"elementId": end} if end else None,
    }
    return key, {
        "id": key,
        "type": "arrow",
        "x": 100,
        "y": 25,
        "width": 100,
        "height": 0,
        **bindings,
        **fields,
    }


CASES: list[dict[str, Any]] = [
    {"case": "empty", "name": "Nothing yet", "elements": {}},
    {
        "case": "a labelled flow",
        "name": "Stack",
        "elements": dict(
            [
                _shape("api", x=0),
                _label("api-label", "api", "API"),
                _shape("db", "ellipse", x=300),
                _label("db-label", "db", "DB"),
                _arrow("reads", "api", "db"),
                _label("reads-label", "reads", "reads"),
                _arrow("loose", None, "db"),
            ]
        ),
    },
    {
        "case": "frames, free text, deleted",
        "name": "Plan",
        "elements": dict(
            [
                (
                    "f1",
                    {
                        "type": "frame",
                        "name": "Phase 1",
                        "x": -50,
                        "y": -50,
                        "width": 500,
                        "height": 400,
                    },
                ),
                ("f2", {"type": "magicframe", "x": 0, "y": 0}),
                ("t1", {"type": "text", "text": "A note", "x": 5, "y": 300}),
                _shape("gone", isDeleted=True),
                ("l1", {"type": "line", "x": 0, "y": 0, "width": 10, "height": 10}),
                ("img", {"type": "image", "x": 1, "y": 1}),
            ]
        ),
    },
    {
        "case": "untrusted words",
        "name": 'Quotes " and \\ backslashes',
        "elements": dict(
            [
                _shape("s1"),
                _label("s1-label", "s1", "<script>alert(1)</script> <b>bold</b>"),
                (
                    "t-bidi",
                    {"type": "text", "text": "safe\u202eexe.txt\u2066x\u2069", "x": 0, "y": 0},
                ),
                (
                    "t-tags",
                    {"type": "text", "text": "hi\U000e0041\U000e007f there", "x": 0, "y": 0},
                ),
                ("t-ctrl", {"type": "text", "text": "a\x1b[31mred\x00\x7f\x9f b", "x": 0, "y": 0}),
                (
                    "t-space",
                    {"type": "text", "text": "x\u00a0\u2003y\x1c\x1fz\n\tw\u3000v", "x": 0, "y": 0},
                ),
                (
                    "t-zwj",
                    {
                        "type": "text",
                        # A woman technologist, joined; and Persian, with its ZWNJ.
                        "text": "\U0001f469\u200d\U0001f4bb "
                        "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645",
                        "x": 0,
                        "y": 0,
                    },
                ),
                (
                    "t-cjk",
                    {
                        "type": "text",
                        "text": "\u8bbe\u8ba1 \u65e5\u672c\u8a9e \ud55c\uad6d\uc5b4",
                        "x": 0,
                        "y": 0,
                    },
                ),
                ("t-long", {"type": "text", "text": "word " * 40, "x": 0, "y": 0}),
                ("t-none", {"type": "text", "text": None, "x": 0, "y": 0}),
            ]
        ),
    },
    *(
        {
            "case": f"bounds: {x!r}, {y!r}",
            "name": "Numbers",
            "elements": dict([_shape("n", x=x, y=y, width=0, height=0)]),
        }
        for x, y in [
            (88.515625, -0.0),
            (1234567, 1234565),
            (123456.5, 999999.5),
            (0.0001, 1e-5),
            (1e21, -1e-7),
            (0.5, 2.5),
            (100000, 1000000),
            (-123.456789, 5e-324),
        ]
    ),
    {
        "case": "what isn't a place is passed over",
        "name": "Numbers",
        "elements": {
            "e": {"type": "rectangle", "x": 1, "y": 1, "width": None},
            "f": {"type": "rectangle", "x": "far", "y": 1},
            "g": {"type": "ellipse", "x": 7, "y": 7},
        },
    },
    {
        "case": "cut past its length",
        "name": "Big",
        "elements": dict(_shape(f"box{n:04}", x=n * 10) for n in range(MAX_DESCRIPTION // 10)),
    },
    {
        "case": "odd shapes of data",
        "name": "Odd",
        "elements": {
            "no-type": {"x": 0, "y": 0},
            "bad-binding": {"type": "arrow", "startBinding": "x", "endBinding": {"elementId": 3}},
            "dangling": {"type": "arrow", "startBinding": {"elementId": "missing"}},
            "labelled-missing": {"type": "text", "containerId": "nobody", "text": "orphan"},
        },
    },
]


def fixture() -> list[dict[str, Any]]:
    """Each case, with the description `describe` writes for it."""
    return [{**case, "description": describe(case["name"], case["elements"])} for case in CASES]


if __name__ == "__main__":
    json.dump(fixture(), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
