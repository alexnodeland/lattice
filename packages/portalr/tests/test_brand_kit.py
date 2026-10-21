"""A brand kit read whole: brand.json, its tokens' floors, its marks and its faces (RFC-0007)."""

import json
import re
import shutil
from pathlib import Path

import pytest

from portalr.brand.colour import Rgba, contrast, delta_e2000, distance, mix
from portalr.brand.kit import FONT_BYTES, FONTS_BYTES, PNG_BYTES, SVG_BYTES, load, svg_faults
from portalr.brand.tokens import BrandError, resolved

EXAMPLES = Path(__file__).parents[1] / "src" / "portalr" / "brand" / "examples"
MARK = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><rect width="8" height="8"/></svg>'
)


@pytest.fixture
def kit(tmp_path: Path) -> Path:
    """A copy of nightshade, to change."""
    copied = tmp_path / "kit"
    shutil.copytree(EXAMPLES / "nightshade", copied)
    return copied


def brand(kit: Path) -> dict:
    return json.loads((kit / "brand.json").read_text())


def write(kit: Path, data: dict, name: str = "brand.json") -> None:
    (kit / name).write_text(json.dumps(data))


def faults(kit: Path) -> str:
    with pytest.raises(BrandError) as raised:
        load(kit)
    return str(raised.value)


@pytest.mark.parametrize("name", ["nightshade", "calm"])
def test_the_example_kits_load(name: str) -> None:
    built = load(EXAMPLES / name)
    assert set(built.files) >= {"brand.css", "assets/mark-light.svg", "assets/favicon.svg"}
    assert re.fullmatch(r"[0-9a-f]{16}", built.hash)
    assert built.files["brand.css"].decode() == built.stylesheet
    assert built.stylesheet.startswith("/*\n * A brand kit's tokens over portalr's default kit")


def test_brand_json_may_name_its_schema(kit: Path) -> None:
    data = brand(kit)
    data["$schema"] = "https://example.com/portalr-brand-1.json"
    write(kit, data)
    assert load(kit).brand.schema_ == "https://example.com/portalr-brand-1.json"


def test_the_hash_changes_with_any_file(kit: Path) -> None:
    before = load(kit).hash
    (kit / "assets" / "favicon.svg").write_bytes(MARK)
    assert load(kit).hash != before


def test_a_kit_without_brand_json_is_refused(tmp_path: Path) -> None:
    assert faults(tmp_path) == "brand.json: a kit has one"


def test_brand_json_is_json_in_utf8(kit: Path) -> None:
    (kit / "brand.json").write_text("{")
    assert faults(kit).startswith("brand.json: not JSON in UTF-8")


def test_brand_json_has_a_closed_shape(kit: Path) -> None:
    data = brand(kit)
    data["copy"]["motto"] = "unknown words"
    data["identity"]["product"] = "x" * 65
    write(kit, data)
    said = faults(kit)
    assert "brand.json: copy.motto: Extra inputs are not permitted" in said
    assert "brand.json: identity.product:" in said


@pytest.mark.parametrize("text", ["Line\nbreak", "Bidi ‮ override", "Bell \x07"])
def test_words_hold_no_control_bidi_or_line_break(kit: Path, text: str) -> None:
    data = brand(kit)
    data["copy"]["tagline"] = text
    write(kit, data)
    assert "a control, format or line-break character" in faults(kit)


def test_a_kit_for_another_inventory_is_refused(kit: Path) -> None:
    data = brand(kit)
    data["version"] = 2
    write(kit, data)
    assert "brand.json: version 2; this portal reads version 1" in faults(kit)


def test_a_token_fault_is_listed_with_the_rest(kit: Path) -> None:
    write(kit, {"color": {"nope": {"$value": "#000000"}}}, "tokens.light.json")
    assert "color.nope: no token has this path" in faults(kit)


def test_text_under_its_contrast_floor_is_refused(kit: Path) -> None:
    write(kit, {"color": {"muted": {"$value": "#c0c0c0"}}}, "tokens.light.json")
    said = faults(kit)
    assert "light: --muted on --paper is" in said
    assert "under 4.5:1 (quiet text)" in said


def test_a_clear_colour_is_read_over_the_paper(kit: Path) -> None:
    clear = {"colorSpace": "srgb", "components": [0, 0, 0], "hex": "#000000", "alpha": 0.1}
    write(kit, {"color": {"edge": {"$value": clear}}}, "tokens.light.json")
    assert "light: --edge on --paper is" in faults(kit)


def test_marks_too_close_to_tell_apart_are_refused(kit: Path) -> None:
    write(kit, {"color": {"chart": {"2": {"$value": "{color.chart.1}"}}}}, "tokens.light.json")
    said = faults(kit)
    assert "light: --chart-1 and --chart-2 are 0.0 apart to every reader, under 20" in said
    assert "to protanopia" in said


def test_motion_past_its_guard_rails_is_refused(kit: Path) -> None:
    write(
        kit,
        {
            "motion": {
                "duration": {
                    "fast": {"$value": {"value": 700, "unit": "ms"}},
                    "pulse": {"$value": {"value": 200, "unit": "ms"}},
                },
                "ease": {"out": {"$value": [0, 1.5, 0.2, 1]}},
            },
            "component": {
                "dialog": {"enter-scale": {"$value": 0.5}},
                "button": {"press-shift": {"$value": {"value": 2, "unit": "rem"}}},
            },
        },
        "tokens.light.json",
    )
    said = faults(kit)
    assert "motion.duration.fast: a change takes 600ms at most" in said
    assert "motion.duration.pulse: a loop is slower than three times a second" in said
    assert "motion.ease.out: an easing overshoots by a tenth at most" in said
    assert "component.dialog.enter-scale: an entry's scale starts from 0.9 to 1" in said
    assert "component.button.press-shift: a press moves 24px at most" in said


def test_under_an_accessibility_floor_is_refused(kit: Path) -> None:
    write(
        kit,
        {
            "component": {"focus": {"width": {"$value": {"value": 1, "unit": "px"}}}},
            "font": {"leading": {"normal": {"$value": 1.2}}},
        },
        "tokens.light.json",
    )
    said = faults(kit)
    assert "component.focus.width: a focus ring is 2px wide or more" in said
    assert "font.leading.normal: body text's leading is 1.4 or more" in said


def test_an_asset_the_kit_doesnt_hold_or_that_leaves_it_is_refused(kit: Path) -> None:
    data = brand(kit)
    data["assets"]["mark"]["light"] = "assets/missing.svg"
    data["assets"]["favicon"] = "assets/..svg"
    write(kit, data)
    said = faults(kit)
    assert "assets/missing.svg: no such file in the kit" in said
    assert "assets/..svg: no such file in the kit" in said


def test_a_favicon_is_an_svg_or_a_png(kit: Path) -> None:
    data = brand(kit)
    (kit / "assets" / "favicon.ico").write_bytes(b"\0\0\1\0")
    (kit / "assets" / "big.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * PNG_BYTES)
    data["assets"]["favicon"] = "assets/favicon.ico"
    data["assets"]["mark"]["dark"] = "assets/big.png"
    write(kit, data)
    said = faults(kit)
    assert "assets/favicon.ico: a mark is an SVG, a favicon an SVG or a PNG" in said
    assert "assets/big.png: a PNG of 128 KB at most" in said


def test_a_png_favicon_is_served(kit: Path) -> None:
    (kit / "assets" / "favicon.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 16)
    data = brand(kit)
    data["assets"]["favicon"] = "assets/favicon.png"
    write(kit, data)
    assert "assets/favicon.png" in load(kit).files


@pytest.mark.parametrize(
    ("svg", "fault"),
    [
        (b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "<script>"),
        (b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>", "onload"),
        (b"<svg xmlns='http://www.w3.org/2000/svg'><style>a{}</style></svg>", "<style>"),
        (
            b"<svg xmlns='http://www.w3.org/2000/svg'><rect fill='url(https://x/y)'/></svg>",
            "url() names something outside the mark",
        ),
        (b"<!DOCTYPE svg [<!ENTITY a 'b'>]><svg/>", "no DOCTYPE or entities"),
        (b"<svg", "not well-formed XML"),
        (b"<svg>" + b" " * SVG_BYTES + b"</svg>", "an SVG is 64 KB at most"),
    ],
)
def test_an_svg_is_held_to_an_allow_list(svg: bytes, fault: str) -> None:
    assert any(fault in each for each in svg_faults("mark.svg", svg))


def test_a_fragment_url_is_allowed_in_an_svg() -> None:
    svg = (
        b"<svg xmlns='http://www.w3.org/2000/svg'><defs><linearGradient id='g'/></defs>"
        b"<rect fill='url(#g)'/></svg>"
    )
    assert svg_faults("mark.svg", svg) == []


def font(kit: Path, files: list[dict], spdx: str = "OFL-1.1") -> None:
    data = brand(kit)
    data["fonts"] = [
        {"family": "Inter", "files": files, "licence": {"spdx": spdx, "file": "fonts/OFL.txt"}}
    ]
    write(kit, data)


def test_a_face_is_built_into_font_face_rules_and_served(kit: Path) -> None:
    (kit / "fonts").mkdir()
    (kit / "fonts" / "OFL.txt").write_text("SIL Open Font License")
    (kit / "fonts" / "inter.woff2").write_bytes(b"wOF2" + b"\0" * 16)
    font(kit, [{"path": "fonts/inter.woff2", "weight": "100 900", "unicode_range": "U+0000-00FF"}])
    built = load(kit)
    assert '@font-face {\n  font-family: "Inter";\n  src: url("fonts/inter.woff2")' in (
        built.stylesheet
    )
    assert "font-display: swap;\n  unicode-range: U+0000-00FF;" in built.stylesheet
    assert {"fonts/inter.woff2", "fonts/OFL.txt"} <= set(built.files)


def test_a_face_is_woff2_within_its_caps_under_a_known_licence(kit: Path) -> None:
    (kit / "fonts").mkdir()
    (kit / "fonts" / "a.ttf").write_bytes(b"\0\1\0\0")
    (kit / "fonts" / "big.woff2").write_bytes(b"wOF2" + b"\0" * FONT_BYTES)
    font(kit, [{"path": "fonts/a.ttf"}, {"path": "fonts/big.woff2"}], spdx="GPL-3.0")
    said = faults(kit)
    assert "Inter: its licence is one of" in said
    assert "fonts/OFL.txt: no such file in the kit" in said
    assert "fonts/a.ttf: a face is a WOFF2 file" in said
    assert "fonts/big.woff2: a face's file is 400 KB at most" in said


def test_a_kits_faces_are_capped_in_all(kit: Path) -> None:
    (kit / "fonts").mkdir()
    (kit / "fonts" / "OFL.txt").write_text("licence")
    files = []
    for at in range(FONTS_BYTES // FONT_BYTES + 1):
        (kit / "fonts" / f"f{at}.woff2").write_bytes(b"wOF2" + b"\0" * (FONT_BYTES - 8))
        files.append({"path": f"fonts/f{at}.woff2"})
    font(kit, files)
    assert "fonts: a kit's faces are 1536 KB at most in all" in faults(kit)


def test_the_colour_arithmetic_is_wcags_and_sharma_wu_and_dalals() -> None:
    assert contrast(Rgba.hex("#000000"), Rgba.hex("#ffffff")) == pytest.approx(21)
    assert delta_e2000((50, 2.6772, -79.7751), (50, 0, -82.7485)) == pytest.approx(2.0425, abs=1e-3)
    assert delta_e2000((50, 2.5, 0), (73, 25, -18)) == pytest.approx(27.1492, abs=1e-3)
    assert delta_e2000((50, 0, 0), (50, 0, 0)) == 0
    assert mix(Rgba(0, 0, 0, 0), 0.5, Rgba(0, 0, 0, 0)) == Rgba(0, 0, 0, 0)
    red, green = Rgba.hex("#ff0000"), Rgba.hex("#00ff00")
    assert distance(red, green) > distance(red, green, "deuteranopia")


def test_a_face_whose_file_is_missing_is_refused(kit: Path) -> None:
    (kit / "fonts").mkdir()
    (kit / "fonts" / "OFL.txt").write_text("licence")
    font(kit, [{"path": "fonts/missing.woff2"}])
    assert "fonts/missing.woff2: no such file in the kit" in faults(kit)


def test_an_alias_cycle_is_refused_where_it_is_resolved() -> None:
    cycle = {"color.paper": "{color.surface}", "color.surface": "{color.paper}"}
    with pytest.raises(BrandError, match="aliases deep, or a cycle"):
        resolved("color.paper", cycle)
