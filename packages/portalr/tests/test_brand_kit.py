"""A brand kit read whole: brand.json, its tokens' floors, its marks and its faces (RFC-0007)."""

import json
import re
import shutil
from pathlib import Path

import pytest

from portalr.brand.colour import Rgba, contrast, delta_e2000, distance, mix
from portalr.brand.inventory import ROWS
from portalr.brand.kit import FONT_BYTES, FONTS_BYTES, PNG_BYTES, SVG_BYTES, load, svg_faults
from portalr.brand.tokens import SWAPPED, BrandError, layered, resolved
from portalr.brand.validate import PAIRS, colour

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
    assert set(built.files) >= {"brand.css", "assets/mark-light.svg", "assets/favicon.png"}
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
    (kit / "assets" / "mark-dark.svg").write_bytes(MARK)
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
    assert "a control, format, blank or line-break character" in faults(kit)


def test_a_name_of_spaces_alone_is_refused(kit: Path) -> None:
    data = brand(kit)
    data["identity"]["app"] = "   "
    write(kit, data)
    assert "is only spaces" in faults(kit)


def test_a_version_is_a_whole_number_not_true(kit: Path) -> None:
    data = brand(kit)
    data["version"] = True
    write(kit, data)
    assert "brand.json: version: Input should be a valid integer" in faults(kit)


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


def test_under_an_accessibility_floor_in_either_scheme_is_refused(kit: Path) -> None:
    write(
        kit,
        {
            "component": {"focus": {"width": {"$value": {"value": 1, "unit": "px"}}}},
            "font": {"leading": {"normal": {"$value": 1.2}}},
        },
        "tokens.light.json",
    )
    said = faults(kit)
    assert "light: component.focus.width: a focus ring is 2px wide or more" in said
    assert "light: font.leading.normal: body text's leading is 1.4 or more" in said


def test_a_floor_broken_in_dark_alone_is_refused(kit: Path) -> None:
    dark = json.loads((kit / "tokens.dark.json").read_text())
    dark["component"] = {"icon-button": {"size": {"$value": {"value": 12, "unit": "px"}}}}
    write(kit, dark, "tokens.dark.json")
    said = faults(kit)
    assert "dark: component.icon-button.size: an icon button is a target 24px or more" in said
    assert "light: component.icon-button.size" not in said


def test_an_asset_the_kit_doesnt_hold_is_refused(kit: Path) -> None:
    data = brand(kit)
    data["assets"]["mark"]["light"] = "assets/missing.svg"
    write(kit, data)
    assert "assets/missing.svg: no such file in the kit" in faults(kit)


def test_an_asset_linked_from_outside_the_kit_is_refused(kit: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.svg"
    outside.write_bytes(MARK)
    (kit / "assets" / "escape.svg").symlink_to(outside)
    data = brand(kit)
    data["assets"]["favicon"] = "assets/escape.svg"
    write(kit, data)
    assert "assets/escape.svg: no such file in the kit" in faults(kit)


def test_an_asset_is_served_by_what_it_is_not_what_it_is_named(kit: Path) -> None:
    (kit / "assets" / "page.html").write_text("<script>alert(1)</script>")
    (kit / "assets" / "page.svg").symlink_to(kit / "assets" / "page.html")
    data = brand(kit)
    data["assets"]["favicon"] = "assets/page.svg"
    write(kit, data)
    assert "assets/page.svg: a plain file of the kit's own, not a link" in faults(kit)


def test_a_favicon_is_an_svg_or_a_png(kit: Path) -> None:
    data = brand(kit)
    (kit / "assets" / "favicon.ico").write_bytes(b"\0\0\1\0")
    (kit / "assets" / "big.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * PNG_BYTES)
    (kit / "assets" / "fake.png").write_bytes(b"GIF89a")
    data["assets"]["favicon"] = "assets/favicon.ico"
    data["assets"]["mark"]["dark"] = "assets/big.png"
    data["assets"]["mark"]["light"] = "assets/fake.png"
    write(kit, data)
    said = faults(kit)
    assert "assets/favicon.ico: a mark or a favicon is an SVG or a PNG" in said
    assert "assets/big.png: larger than 128 KB" in said
    assert "assets/fake.png: not a PNG" in said


def test_a_png_favicon_is_served(kit: Path) -> None:
    (kit / "assets" / "favicon.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 16)
    data = brand(kit)
    data["assets"]["favicon"] = "assets/favicon.png"
    write(kit, data)
    assert "assets/favicon.png" in load(kit).files


SVG = b"<svg xmlns='http://www.w3.org/2000/svg'"


@pytest.mark.parametrize(
    ("svg", "fault"),
    [
        (SVG + b"><script>alert(1)</script></svg>", "script'> isn't allowed"),
        (SVG + b" onload='alert(1)'/>", "the attribute 'onload'"),
        (SVG + b"><style>a{}</style></svg>", "style'> isn't allowed"),
        (SVG + b"><foreignObject/></svg>", "foreignObject'> isn't allowed"),
        (SVG + b"><use href='#a'/></svg>", "use'> isn't allowed"),
        (SVG + b"><image href='x.png'/></svg>", "image'> isn't allowed"),
        (
            SVG + b" xmlns:x='http://www.w3.org/1999/xlink'><rect x:href='javascript:1'/></svg>",
            "the attribute '{http://www.w3.org/1999/xlink}href'",
        ),
        (SVG + b"><rect fill='url(https://x/y)'/></svg>", "'fill' names something outside"),
        (SVG + b"><rect fill='URL(https://x/y)'/></svg>", "'fill' names something outside"),
        (SVG + b"><rect fill='\\75rl(https://x)'/></svg>", "'fill' holds a backslash"),
        (SVG + b"><rect fill='javascript:alert(1)'/></svg>", "'fill' names something outside"),
        (b"<!DOCTYPE svg [<!ENTITY a 'b'>]>" + SVG + b"/>", "an SVG declares nothing"),
        (b"<?xml-stylesheet href='https://x/y.css'?>" + SVG + b"/>", "an SVG declares nothing"),
        (SVG + b"><![CDATA[x]]></svg>", "an SVG declares nothing"),
        ("<svg/>".encode("utf-16"), "UTF-8 with no byte-order mark"),
        (b"\xef\xbb\xbf" + SVG + b"/>", "UTF-8 with no byte-order mark"),
        (b"<svg>\xff</svg>", "an SVG is UTF-8"),
        (b"<svg/>", "an <svg> in the SVG namespace"),
        (b"<html xmlns='http://www.w3.org/2000/svg'/>", "an <svg> in the SVG namespace"),
        (SVG + b"><x:rect xmlns:x='urn:other'/></svg>", "{urn:other}rect'> isn't allowed"),
        (b"<svg", "not well-formed XML"),
        (b"<svg>" + b" " * SVG_BYTES + b"</svg>", "an SVG is 64 KB at most"),
    ],
)
def test_an_svg_is_held_to_an_allow_list(svg: bytes, fault: str) -> None:
    assert any(fault in each for each in svg_faults("mark.svg", svg)), svg_faults("mark.svg", svg)


def test_a_fragment_url_a_comment_and_the_declaration_are_allowed_in_an_svg() -> None:
    svg = (
        b"<?xml version='1.0' encoding='UTF-8'?><!-- a mark -->" + SVG + b"><defs>"
        b"<linearGradient id='g'/></defs><rect fill='url(#g)'/></svg>"
    )
    assert svg_faults("mark.svg", svg) == []


def woff2(size: int = 64) -> bytes:
    """A WOFF2 header that describes a file of `size` bytes, one table and a font."""
    header = b"wOF2" + b"\0\1\0\0" + size.to_bytes(4, "big") + (1).to_bytes(2, "big")
    header += b"\0\0" + (1024).to_bytes(4, "big")
    return header + b"\0" * (size - len(header))


def font(
    kit: Path, files: list[dict], spdx: str = "OFL-1.1", licence: str = "fonts/OFL.txt"
) -> None:
    data = brand(kit)
    data["fonts"] = [
        {"family": "Inter", "files": files, "licence": {"spdx": spdx, "file": licence}}
    ]
    write(kit, data)


def test_a_face_is_built_into_font_face_rules_and_served(kit: Path) -> None:
    (kit / "fonts").mkdir()
    (kit / "fonts" / "OFL.txt").write_text("SIL Open Font License")
    (kit / "fonts" / "inter.woff2").write_bytes(woff2())
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
    (kit / "fonts" / "big.woff2").write_bytes(woff2(FONT_BYTES + 64))
    (kit / "fonts" / "magic.woff2").write_bytes(b"wOF2" + b"\0" * 60)
    (kit / "fonts" / "short.woff2").write_bytes(b"wOF2")
    font(
        kit,
        [
            {"path": "fonts/a.ttf"},
            {"path": "fonts/big.woff2"},
            {"path": "fonts/magic.woff2"},
            {"path": "fonts/short.woff2"},
        ],
        spdx="GPL-3.0",
    )
    said = faults(kit)
    assert "Inter: its licence is one of" in said
    assert "fonts/OFL.txt: no such file in the kit" in said
    assert "fonts/a.ttf: a face is a .woff2 file" in said
    assert "fonts/big.woff2: larger than 400 KB" in said
    assert "fonts/magic.woff2: a WOFF2 header that doesn't describe its file" in said
    assert "fonts/short.woff2: a face is a WOFF2 file" in said


def test_a_licence_is_a_capped_txt_file(kit: Path) -> None:
    (kit / "fonts").mkdir()
    (kit / "fonts" / "inter.woff2").write_bytes(woff2())
    (kit / "fonts" / "OFL.svg").write_bytes(MARK)
    font(kit, [{"path": "fonts/inter.woff2"}], licence="fonts/OFL.svg")
    assert "fonts/OFL.svg: a licence is a .txt file" in faults(kit)
    (kit / "fonts" / "OFL.txt").write_text("x" * (65 * 1024))
    font(kit, [{"path": "fonts/inter.woff2"}])
    assert "fonts/OFL.txt: larger than 64 KB" in faults(kit)


def test_a_kits_faces_are_capped_in_number_and_in_all(kit: Path) -> None:
    (kit / "fonts").mkdir()
    (kit / "fonts" / "OFL.txt").write_text("licence")
    files = []
    for at in range(FONTS_BYTES // FONT_BYTES + 1):
        (kit / "fonts" / f"f{at}.woff2").write_bytes(woff2(FONT_BYTES - 64))
        files.append({"path": f"fonts/f{at}.woff2"})
    font(kit, files)
    assert "fonts: a kit's faces and licences are 1536 KB at most" in faults(kit)
    data = brand(kit)
    data["fonts"] = [
        {
            "family": "Inter",
            "files": [{"path": "fonts/f0.woff2"}] * 9,
            "licence": {"spdx": "MIT", "file": "fonts/OFL.txt"},
        }
    ] * 2
    write(kit, data)
    assert "fonts: a kit brings 16 face files at most" in faults(kit)


def test_a_face_whose_file_is_missing_is_refused(kit: Path) -> None:
    (kit / "fonts").mkdir()
    (kit / "fonts" / "OFL.txt").write_text("licence")
    font(kit, [{"path": "fonts/missing.woff2"}])
    assert "fonts/missing.woff2: no such file in the kit" in faults(kit)


def test_a_json_file_is_capped_and_the_kits_own(kit: Path, tmp_path: Path) -> None:
    (kit / "tokens.dark.json").write_text(" " * (257 * 1024))
    assert "tokens.dark.json: larger than 256 KB" in faults(kit)
    (kit / "tokens.dark.json").unlink()
    (tmp_path / "elsewhere.json").write_text("{}")
    (kit / "tokens.dark.json").symlink_to(tmp_path / "elsewhere.json")
    assert "tokens.dark.json: a plain file of the kit's own" in faults(kit)


def test_what_colour_blind_mode_swaps_is_declared_outside_it(kit: Path) -> None:
    css = load(kit).stylesheet
    block = css.split(":root:not([data-cvd]) {", 1)[1].split("}", 1)[0]
    assert {line.split(":")[0].strip() for line in block.strip().splitlines()} == set(SWAPPED)
    root = css.split(":root {", 1)[1].split("\n}", 1)[0]
    assert "--chart-1:" not in root


def test_the_swapped_tokens_are_base_csss_colour_blind_ones() -> None:
    base = (Path(__file__).parents[1] / "web" / "ui" / "src" / "base.css").read_text()
    block = base.split("[data-cvd] {", 1)[1].split("\n}", 1)[0]
    declared = set(re.findall(r"^\s*(--[a-z0-9-]+):", block, re.M))
    tokens = {row.prop for row in ROWS.values()}
    assert declared & tokens == set(SWAPPED)


def test_a_danger_on_its_wash_is_held_over_each_backdrop() -> None:
    pairs = json.loads(PAIRS.read_text())["pairs"]
    backdrops = {
        p.get("backdrop") for p in pairs if (p["fg"], p["bg"]) == ("danger", "danger-wash")
    }
    assert backdrops == {"paper", "surface"}
    light, _ = layered()
    assert colour("danger-wash", light, "surface") != colour("danger-wash", light, "paper")


def test_the_colour_arithmetic_is_wcags_and_sharma_wu_and_dalals() -> None:
    assert contrast(Rgba.hex("#000000"), Rgba.hex("#ffffff")) == pytest.approx(21)
    assert contrast(Rgba.hex("#767676"), Rgba.hex("#ffffff")) == pytest.approx(4.54, abs=0.01)
    assert delta_e2000((50, 2.6772, -79.7751), (50, 0, -82.7485)) == pytest.approx(2.0425, abs=1e-3)
    assert delta_e2000((50, 2.5, 0), (73, 25, -18)) == pytest.approx(27.1492, abs=1e-3)
    # Sharma, Wu and Dalal's pairs where the hues wrap around 0 and 360 degrees.
    assert delta_e2000((50, 2.5, 0), (50, 0, -2.5)) == pytest.approx(4.3065, abs=1e-3)
    assert delta_e2000((50, 2.49, -0.001), (50, -2.49, 0.0009)) == pytest.approx(7.1792, abs=1e-3)
    assert delta_e2000((50, -0.001, 2.49), (50, 0.0009, -2.49)) == pytest.approx(4.8045, abs=1e-3)
    assert delta_e2000((50, 0, 0), (50, 0, 0)) == 0
    assert mix(Rgba(0, 0, 0, 0), 0.5, Rgba(0, 0, 0, 0)) == Rgba(0, 0, 0, 0)
    red, green = Rgba.hex("#ff0000"), Rgba.hex("#00ff00")
    assert distance(red, green) > distance(red, green, "deuteranopia")
    # Machado's protanopia moves pure red to a dark yellow-brown (their published simulation).
    assert distance(red, Rgba.hex("#6e5e00"), "protanopia") < distance(red, Rgba.hex("#6e5e00"))


def test_an_alias_cycle_is_refused_where_it_is_resolved() -> None:
    cycle = {"color.paper": "{color.surface}", "color.surface": "{color.paper}"}
    with pytest.raises(BrandError, match="aliases deep, or a cycle"):
        resolved("color.paper", cycle)


def test_a_key_that_would_forge_a_log_line_is_said_as_its_repr(kit: Path) -> None:
    data = brand(kit)
    data["identity"]["x\nERROR forged\x1b[0m"] = "y"
    write(kit, data)
    said = faults(kit)
    assert "identity.'x\\nERROR forged\\x1b[0m'" in said
    assert "\nERROR forged" not in said


def test_a_brand_json_nested_too_deep_is_refused(
    kit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Python 3.14's parser takes any depth, so the depth is forced, as on 3.12 and 3.13.
    def deep(*_: object, **__: object) -> object:
        raise RecursionError

    monkeypatch.setattr("portalr.brand.kit.Brand.model_validate", deep)
    assert faults(kit) == "brand.json: nested too deep"


def test_a_kit_names_sixteen_faces_at_most(kit: Path) -> None:
    data = brand(kit)
    one = {
        "family": "Inter",
        "files": [{"path": "fonts/a.woff2"}],
        "licence": {"spdx": "MIT", "file": "fonts/L.txt"},
    }
    data["fonts"] = [one] * 17
    write(kit, data)
    said = faults(kit)
    assert "brand.json: fonts:" in said
    assert "16" in said


def test_a_licence_two_faces_share_is_read_once(kit: Path) -> None:
    (kit / "fonts").mkdir()
    (kit / "fonts" / "OFL.txt").write_text("licence")
    (kit / "fonts" / "a.woff2").write_bytes(woff2())
    (kit / "fonts" / "b.woff2").write_bytes(woff2())
    data = brand(kit)
    data["fonts"] = [
        {
            "family": family,
            "files": [{"path": path}],
            "licence": {"spdx": "OFL-1.1", "file": "fonts/OFL.txt"},
        }
        for family, path in (("Inter", "fonts/a.woff2"), ("Inter Display", "fonts/b.woff2"))
    ]
    write(kit, data)
    assert list(load(kit).files).count("fonts/OFL.txt") == 1


def test_a_token_file_nested_too_deep_is_refused(
    kit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (kit / "tokens.light.json").write_text("{}")

    def deep(*_: object, **__: object) -> object:
        raise RecursionError

    monkeypatch.setattr("portalr.brand.tokens._mapping", deep)
    assert faults(kit) == "tokens.light.json: nested too deep"


def test_a_loop_of_links_is_a_fault_on_every_python(kit: Path) -> None:
    (kit / "assets" / "mark-dark.svg").unlink()
    (kit / "assets" / "mark-dark.svg").symlink_to(kit / "assets" / "mark-dark.svg")
    # 3.12's resolve() finds the loop; 3.13's leaves it to the open, which refuses the link.
    said = faults(kit)
    assert (
        "assets/mark-dark.svg: no such file in the kit" in said
        or "assets/mark-dark.svg: a plain file of the kit's own, not a link" in said
    )


def test_a_path_that_cant_be_resolved_is_no_file_of_the_kits(
    kit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Python 3.12 raises on a loop of links where 3.13 doesn't: held here on every version.
    real = Path.resolve

    def looping(self: Path, strict: bool = False) -> Path:
        if self.name == "mark-dark.svg":
            raise RuntimeError("Symlink loop")
        return real(self, strict)

    monkeypatch.setattr(Path, "resolve", looping)
    assert "assets/mark-dark.svg: no such file in the kit" in faults(kit)


def test_a_link_inside_the_kit_is_refused_too(kit: Path) -> None:
    (kit / "assets" / "mark-light.svg").unlink()
    (kit / "assets" / "mark-light.svg").symlink_to(kit / "assets" / "mark-dark.svg")
    assert "assets/mark-light.svg: a plain file of the kit's own, not a link" in faults(kit)


def test_a_file_that_fails_as_it_is_read_is_a_fault(
    kit: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(*_: object, **__: object) -> object:
        raise OSError(5, "Input/output error")

    monkeypatch.setattr("portalr.brand.tokens.os.fdopen", failing)
    assert "brand.json: can't be read (Input/output error)" in faults(kit)
