"""A brand kit, read and checked whole, and built into what the portal serves (lattice RFC-0007).

A kit is a folder: ``brand.json`` (its identity, its words, its marks and its fonts with their
licences), its DTCG tokens over the default's, and its files. :func:`load` reads all of it,
refuses it with every fault listed, and returns a :class:`Kit`: the stylesheet, the files served
beside it by their published paths, a hash of all of it, and the block ``config.json`` carries.
"""

import hashlib
import json
import re
import unicodedata
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from portalr.brand.colour import Rgba
from portalr.brand.inventory import VERSION
from portalr.brand.tokens import DEFAULT, BrandError, compile_kit, layered
from portalr.brand.validate import colour, token_faults

SVG_BYTES = 64 * 1024
PNG_BYTES = 128 * 1024
FONT_BYTES = 400 * 1024
FONTS_BYTES = 1536 * 1024
LICENCES = frozenset({"OFL-1.1", "Apache-2.0", "MIT", "LicenseRef-commercial"})
"""The font licences a kit may name, by SPDX id; a commercial one with its own file."""

_NAME = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
_FAMILY = re.compile(r"^[A-Za-z0-9 -]{1,64}$")
_RANGE = re.compile(
    r"^U\+[0-9A-Fa-f?]{1,6}(-[0-9A-Fa-f]{1,6})?(, ?U\+[0-9A-Fa-f?]{1,6}(-[0-9A-Fa-f]{1,6})?)*$"
)
_WEIGHT = re.compile(r"^[1-9]00( [1-9]00)?$")
_PATH = re.compile(r"^(assets|fonts)/[A-Za-z0-9._-]{1,64}$")


def _plain(text: str) -> str:
    """Refuse what text in a page must never hold: control characters, bidi overrides, newlines."""
    for character in text:
        if unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}:
            raise ValueError(f"{text!r} holds a control, format or line-break character")
    return text


Name = Annotated[str, StringConstraints(min_length=1, max_length=64)]
Copy = Annotated[str, StringConstraints(min_length=1, max_length=200)]
KitPath = Annotated[str, StringConstraints(pattern=_PATH.pattern)]


class Identity(BaseModel):
    """What the product is called: in the tab, in the header, and the admin UI's own name."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    product: Name
    app: Name
    admin: Name


class Words(BaseModel):
    """The words a kit may set: a closed set the UIs read; an unknown one is refused."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)
    tagline: Copy | None = None
    sign_in: Copy | None = Field(default=None, alias="signIn")


class Marks(BaseModel):
    """The header's mark in each scheme, by its path in the kit."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    light: KitPath
    dark: KitPath


class Assets(BaseModel):
    """The kit's marks and its favicon."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    mark: Marks
    favicon: KitPath


class FontFile(BaseModel):
    """One file of a face: its path, its weight or range of them, its style, and its characters."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    path: KitPath
    weight: Annotated[str, StringConstraints(pattern=_WEIGHT.pattern)] = "400"
    style: Literal["normal", "italic"] = "normal"
    unicode_range: Annotated[str, StringConstraints(pattern=_RANGE.pattern)] | None = None


class Licence(BaseModel):
    """A face's licence: its SPDX id, and its text in the kit."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    spdx: str
    file: KitPath


class Font(BaseModel):
    """A face the kit brings, its files and the licence it is under."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    family: Annotated[str, StringConstraints(pattern=_FAMILY.pattern)]
    files: tuple[FontFile, ...]
    licence: Licence


class Brand(BaseModel):
    """``brand.json``: who the kit is, in words, marks and faces."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_: str | None = Field(default=None, alias="$schema")
    """The schema an editor checks the file by; the loader reads it no further."""
    version: int
    name: Annotated[str, StringConstraints(pattern=_NAME.pattern)]
    identity: Identity
    copy_: Words = Field(default=Words(), alias="copy")
    assets: Assets
    fonts: tuple[Font, ...] = ()


@dataclass(frozen=True)
class Kit:
    """A kit, read and checked: what the portal serves of it, and what ``config.json`` says."""

    brand: Brand
    stylesheet: str
    files: dict[str, bytes] = field(repr=False)
    """Every file served, by its path under the kit's hash: ``brand.css``, the marks, the fonts."""
    hash: str
    theme: tuple[str, str]
    """The paper in light and in dark, as ``#rrggbb``, for the page's ``theme-color``."""

    @property
    def base(self) -> str:
        """Where its files are served, under the portal's mount."""
        return f"brand/{self.hash}/"

    def config(self) -> dict[str, object]:
        """The ``config.json`` block: the identity, the words, and where the files are."""
        return {
            "hash": self.hash,
            "identity": self.brand.identity.model_dump(),
            "copy": {
                key: value
                for key, value in {
                    "tagline": self.brand.copy_.tagline,
                    "signIn": self.brand.copy_.sign_in,
                }.items()
                if value is not None
            },
            "stylesheet": f"{self.base}brand.css",
            "mark": {
                "light": f"{self.base}{self.brand.assets.mark.light}",
                "dark": f"{self.base}{self.brand.assets.mark.dark}",
            },
            "favicon": f"{self.base}{self.brand.assets.favicon}",
        }


SVG_ELEMENTS = frozenset(
    {
        "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "title",
        "desc", "defs", "linearGradient", "radialGradient", "stop", "clipPath", "mask",
    }
)  # fmt: skip
SVG_ATTRIBUTES = frozenset(
    {
        "xmlns", "version", "viewBox", "width", "height", "x", "y", "x1", "y1", "x2", "y2", "cx",
        "cy", "r", "rx", "ry", "d", "points", "fill", "fill-rule", "fill-opacity", "clip-rule",
        "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-opacity",
        "stroke-miterlimit", "stroke-dasharray", "opacity", "transform", "id", "offset",
        "stop-color", "stop-opacity", "gradientUnits", "gradientTransform", "clip-path", "mask",
        "role", "aria-label", "aria-hidden", "focusable", "preserveAspectRatio",
    }
)  # fmt: skip
_URL = re.compile(r"url\(\s*([^)]*)\)")


def svg_faults(name: str, data: bytes) -> list[str]:
    """An SVG's faults, by an allow-list: no script, no styles, nothing fetched, no entities."""
    if len(data) > SVG_BYTES:
        return [f"{name}: an SVG is {SVG_BYTES // 1024} KB at most"]
    text = data.decode("utf-8", errors="replace")
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        return [f"{name}: an SVG declares no DOCTYPE or entities"]
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        return [f"{name}: not well-formed XML ({error})"]
    faults: list[str] = []
    for element in root.iter():
        tag = element.tag.split("}")[-1]
        if tag not in SVG_ELEMENTS:
            faults.append(f"{name}: <{tag}> isn't allowed in a mark")
        for attribute, value in element.attrib.items():
            local = attribute.split("}")[-1]
            if local not in SVG_ATTRIBUTES:
                faults.append(f"{name}: the attribute {local} isn't allowed in a mark")
            faults.extend(
                f"{name}: url() names something outside the mark"
                for target in _URL.findall(value)
                if not target.strip(" '\"").startswith("#")
            )
    return faults


def _file(kit: Path, path: str, faults: list[str]) -> bytes | None:
    """A kit's file by its path in brand.json, or a fault if it isn't there or leaves the kit."""
    resolved = (kit / path).resolve()
    if not resolved.is_relative_to(kit.resolve()) or not resolved.is_file():
        faults.append(f"{path}: no such file in the kit")
        return None
    return resolved.read_bytes()


def _asset(kit: Path, path: str, faults: list[str]) -> bytes | None:
    data = _file(kit, path, faults)
    if data is None:
        return None
    if path.endswith(".svg"):
        faults.extend(svg_faults(path, data))
    elif path.endswith(".png"):
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > PNG_BYTES:
            faults.append(f"{path}: a PNG of {PNG_BYTES // 1024} KB at most")
    else:
        faults.append(f"{path}: a mark is an SVG, a favicon an SVG or a PNG")
    return data


def _fonts(kit: Path, brand: Brand, files: dict[str, bytes], faults: list[str]) -> list[str]:
    """Each face's files, checked as WOFF2 within the caps, and its ``@font-face`` rules."""
    rules: list[str] = []
    total = 0
    for font in brand.fonts:
        if font.licence.spdx not in LICENCES:
            faults.append(f"{font.family}: its licence is one of {', '.join(sorted(LICENCES))}")
        licence = _file(kit, font.licence.file, faults)
        if licence is not None:
            files[font.licence.file] = licence
        for each in font.files:
            data = _file(kit, each.path, faults)
            if data is None:
                continue
            total += len(data)
            if not data.startswith(b"wOF2"):
                faults.append(f"{each.path}: a face is a WOFF2 file")
            if len(data) > FONT_BYTES:
                faults.append(f"{each.path}: a face's file is {FONT_BYTES // 1024} KB at most")
            files[each.path] = data
            ranged = f"\n  unicode-range: {each.unicode_range};" if each.unicode_range else ""
            rules.append(
                f'@font-face {{\n  font-family: "{font.family}";\n'
                f'  src: url("{each.path}") format("woff2");\n'
                f"  font-weight: {each.weight};\n  font-style: {each.style};\n"
                f"  font-display: swap;{ranged}\n}}"
            )
    if total > FONTS_BYTES:
        faults.append(f"fonts: a kit's faces are {FONTS_BYTES // 1024} KB at most in all")
    return rules


def load(kit: Path) -> Kit:
    """Read a kit and check all of it: its brand.json, its tokens, its marks and its faces.

    Raises:
        BrandError: With every fault, one to a line, if the kit isn't one the portal can serve.
    """
    faults: list[str] = []
    try:
        raw = json.loads((kit / "brand.json").read_text(encoding="utf-8"))
        brand = Brand.model_validate(raw)
    except FileNotFoundError:
        raise BrandError("brand.json: a kit has one") from None
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BrandError(f"brand.json: not JSON in UTF-8 ({error})") from error
    except ValidationError as error:
        raise BrandError(
            "\n".join(
                f"brand.json: {'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()
            )
        ) from error
    for text in (
        *brand.identity.model_dump().values(),
        *(t for t in (brand.copy_.tagline, brand.copy_.sign_in) if t is not None),
    ):
        try:
            _plain(text)
        except ValueError as error:
            faults.append(f"brand.json: {error}")
    if brand.version != VERSION:
        faults.append(f"brand.json: version {brand.version}; this portal reads version {VERSION}")
    theme = ("#ffffff", "#000000")
    try:
        css = compile_kit(kit)
        light, dark = layered(kit, default=DEFAULT)
        faults.extend(token_faults(light, dark))
        theme = (_hex(colour("paper", light)), _hex(colour("paper", dark)))
    except BrandError as error:
        faults.extend(str(error).splitlines())
        css = ""
    files: dict[str, bytes] = {}
    for path in (brand.assets.mark.light, brand.assets.mark.dark, brand.assets.favicon):
        data = _asset(kit, path, faults)
        if data is not None:
            files[path] = data
    rules = _fonts(kit, brand, files, faults)
    if faults:
        raise BrandError("\n".join(faults))
    stylesheet = "\n\n".join([css.rstrip("\n"), *rules]) + "\n"
    files["brand.css"] = stylesheet.encode()
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.encode() + b"\0" + hashlib.sha256(files[path]).digest())
    digest.update(brand.model_dump_json().encode())
    return Kit(
        brand=brand, stylesheet=stylesheet, files=files, hash=digest.hexdigest()[:16], theme=theme
    )


def _hex(drawn: Rgba) -> str:
    return "#" + "".join(f"{round(c * 255):02x}" for c in (drawn.r, drawn.g, drawn.b))
