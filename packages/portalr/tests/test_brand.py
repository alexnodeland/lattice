"""The default brand kit, and the grammar a kit's tokens are read by (lattice RFC-0007)."""

import importlib
import json
import re
import runpy
import sys
from pathlib import Path

import pytest

from portalr.brand import DEFAULT, BrandError, compile_kit
from portalr.brand.__main__ import main
from portalr.brand.inventory import ROWS

TOKENS = Path(__file__).parent.parent / "web" / "ui" / "src" / "tokens.css"


def test_tokens_css_is_the_default_kit_compiled() -> None:
    """The UIs' tokens are generated: `moon run portalr:brand` writes them again after a change."""
    assert TOKENS.read_text() == compile_kit(), "run `moon run portalr:brand`"


def test_the_default_kit_sets_every_token_and_no_other() -> None:
    light = json.loads((DEFAULT / "tokens.light.json").read_text())

    def paths(tree: dict, at: str = "") -> set[str]:
        found: set[str] = set()
        for key, node in tree.items():
            if key.startswith("$"):
                continue
            path = f"{at}.{key}" if at else key
            found |= {path} if "$value" in node else paths(node, path)
        return found

    assert paths(light) == set(ROWS)


def kit(tmp_path: Path, light: dict, dark: dict | None = None) -> Path:
    (tmp_path / "tokens.light.json").write_text(json.dumps(light))
    if dark is not None:
        (tmp_path / "tokens.dark.json").write_text(json.dumps(dark))
    return tmp_path


def test_a_kit_sets_only_what_it_changes(tmp_path: Path) -> None:
    css = compile_kit(kit(tmp_path, {"radius": {"3": {"$value": {"value": 0, "unit": "rem"}}}}))
    assert "  --radius-3: 0;" in css
    assert "  --paper: light-dark(#fafafb, #121317);" in css


def test_light_holds_in_dark_unless_dark_says_otherwise(tmp_path: Path) -> None:
    """A kit's light tokens are both schemes'; its dark file holds only what differs."""
    css = compile_kit(
        kit(
            tmp_path,
            {"color": {"paper": {"$value": "#ffffff"}, "surface": {"$value": "#fefefe"}}},
            {
                "color": {"surface": {"$value": "#000000"}},
                "radius": {"2": {"$value": {"value": 1, "unit": "px"}}},
            },
        )
    )
    assert "  --paper: #ffffff;" in css
    assert "  --surface: light-dark(#fefefe, #000000);" in css
    assert '  :root:not([data-theme="light"]) {\n    --radius-2: 1px;' in css
    assert ':root[data-theme="dark"] {\n  --radius-2: 1px;' in css


def test_an_alias_is_its_tokens_custom_property(tmp_path: Path) -> None:
    css = compile_kit(kit(tmp_path, {"color": {"accent": {"$value": "{color.chart.3}"}}}))
    assert "  --accent: var(--chart-3);" in css


def test_a_described_group_an_opaque_colour_and_a_shadow_of_a_colour(tmp_path: Path) -> None:
    light = {
        "$description": "A kit's notes are its own.",
        "color": {
            "paper": {
                "$value": {
                    "colorSpace": "srgb",
                    "components": [1, 1, 1],
                    "hex": "#ffffff",
                    "alpha": 1,
                }
            }
        },
        "shadow": {
            "1": {
                "$value": {
                    "color": "#000000",
                    "offsetX": {"value": 0, "unit": "px"},
                    "offsetY": {"value": 1, "unit": "px"},
                    "blur": {"value": 2, "unit": "px"},
                    "spread": {"value": 0, "unit": "px"},
                }
            }
        },
    }
    css = compile_kit(kit(tmp_path, light))
    assert "  --paper: #ffffff;" in css
    assert "  --shadow-1: 0 1px 2px #000000;" in css


def test_a_token_file_is_json_in_utf8(tmp_path: Path) -> None:
    (tmp_path / "tokens.light.json").write_text("{")
    with pytest.raises(BrandError, match=re.escape("tokens.light.json: not JSON in UTF-8")):
        compile_kit(tmp_path)
    (tmp_path / "tokens.light.json").write_bytes(b'{"\xff": 1}')
    with pytest.raises(BrandError, match=re.escape("tokens.light.json: not JSON in UTF-8")):
        compile_kit(tmp_path)


CHAIN = (
    "paper",
    "surface",
    "fg",
    "muted",
    "line",
    "on-accent",
    "focus",
    "edge",
    "on-danger",
    "scrim",
)


def chain(depth: int) -> dict:
    """`depth` aliases, one to the next, the last naming a colour."""
    links = {
        name: {"$value": f"{{color.{CHAIN[at + 1]}}}"} for at, name in enumerate(CHAIN[:depth])
    }
    return {"color": {**links, CHAIN[depth]: {"$value": "#000000"}}}


def test_an_alias_chain_is_eight_deep_at_most(tmp_path: Path) -> None:
    assert "  --paper: var(--surface);" in compile_kit(kit(tmp_path, chain(8)))
    with pytest.raises(BrandError, match="more than 8 aliases deep"):
        compile_kit(kit(tmp_path, chain(9)))


def test_a_token_file_is_an_object(tmp_path: Path) -> None:
    (tmp_path / "tokens.light.json").write_text("[]")
    with pytest.raises(BrandError, match=re.escape("tokens.light.json: a token file is an object")):
        compile_kit(tmp_path)


def test_the_default_kit_holds_every_token(tmp_path: Path) -> None:
    (tmp_path / "tokens.light.json").write_text("{}")
    with pytest.raises(
        BrandError, match=re.escape("color.paper: the default kit has no value for it")
    ):
        compile_kit(tmp_path, default=tmp_path)


def test_the_module_writes_the_default_kits_stylesheet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "tokens.css"
    monkeypatch.setattr(sys, "argv", ["portalr.brand", str(out)])
    # Run afresh, as `python -m` runs it, not as the module this test imported.
    monkeypatch.delitem(sys.modules, "portalr.brand.__main__")
    runpy.run_module("portalr.brand", run_name="__main__")
    assert out.read_text() == compile_kit()
    with pytest.raises(SystemExit, match=re.escape("usage: python -m portalr.brand <tokens.css>")):
        main(["portalr.brand"])


def test_the_module_imports_without_writing() -> None:
    """Importing it, as the standalone check imports every module, writes nothing."""
    module = importlib.import_module("portalr.brand.__main__")
    assert module.main is main


@pytest.mark.parametrize(
    ("light", "fault"),
    [
        ({"color": {"nope": {"$value": "#ffffff"}}}, "color.nope: no token has this path"),
        ({"color": {"paper": {"$value": "red"}}}, "color.paper: a colour is #rrggbb"),
        ({"color": {"paper": {"$value": "#fff;}"}}}, "color.paper: a colour is #rrggbb"),
        ({"color": {"paper": {"$value": "{radius.2}"}}}, "is a dimension, not a color"),
        ({"color": {"paper": {"$value": "{color.nope}"}}}, "names no token"),
        ({"radius": {"2": {"$value": {"value": 1, "unit": "em"}}}}, "is in rem or px"),
        ({"font": {"family": {"sans": {"$value": ['A"; } x {', "serif"]}}}}, "more than letters"),
        ({"font": {"family": {"sans": {"$value": ["Inter"]}}}}, "ends in a generic family"),
        ({"motion": {"ease": {"in": {"$value": [2, 0, 1, 1]}}}}, "x values are from 0 to 1"),
        ({"font": {"weight": {"medium": {"$value": 550}}}}, "a weight is 100 to 900"),
        ({"color": {"paper": "#ffffff"}}, "color.paper: a token is an object with a \\$value"),
        ({"font": {"leading": {"tight": {"$value": "1"}}}}, "'1' is not a number"),
        ({"radius": {"2": {"$value": 2}}}, "a dimension is {value, unit}"),
        ({"color": {"paper": {"$value": {"colorSpace": "srgb", "hex": "red"}}}}, "not a colour"),
        (
            {
                "color": {
                    "paper": {
                        "$value": {
                            "colorSpace": "srgb",
                            "components": [1, 1, 1],
                            "hex": "#ffffff",
                            "alpha": 2,
                        }
                    }
                }
            },
            "an alpha is from 0 to 1",
        ),
        ({"font": {"family": {"sans": {"$value": "Inter"}}}}, "a font family is a list of names"),
        ({"shadow": {"1": {"$value": {"color": "#000000"}}}}, "a shadow is"),
        ({"motion": {"ease": {"in": {"$value": [0, 0, 1]}}}}, "an easing is four numbers"),
        (
            {"color": {"paper": {"$value": "#ffffff", "$type": "dimension"}}},
            "a color, not a dimension",
        ),
        ({"radius": {"$type": "color", "2": {"$value": "#ffffff"}}}, "a dimension, not a color"),
        (
            {"color": {"paper": {"$value": {"colorSpace": "srgb", "hex": "#ffffff"}}}},
            "has three components",
        ),
        (
            {
                "color": {
                    "paper": {
                        "$value": {
                            "colorSpace": "srgb",
                            "components": [0, 0, "x"],
                            "hex": "#000000",
                        }
                    }
                }
            },
            "has three components",
        ),
        (
            {
                "color": {
                    "paper": {
                        "$value": {"colorSpace": "srgb", "components": [0, 0, 0], "hex": "#ffffff"}
                    }
                }
            },
            "its components and its hex are different colours",
        ),
        ({"color": {"paper": {"$value": {"colorSpace": "display-p3"}}}}, "or an srgb object"),
    ],
)
def test_a_kit_the_grammar_refuses(tmp_path: Path, light: dict, fault: str) -> None:
    with pytest.raises(BrandError, match=fault.replace("(", r"\(").replace(")", r"\)")):
        compile_kit(kit(tmp_path, light))


def test_an_alias_cycle_is_refused(tmp_path: Path) -> None:
    light = {
        "color": {"paper": {"$value": "{color.surface}"}, "surface": {"$value": "{color.paper}"}}
    }
    with pytest.raises(BrandError, match="aliases deep, or a cycle"):
        compile_kit(kit(tmp_path, light))
