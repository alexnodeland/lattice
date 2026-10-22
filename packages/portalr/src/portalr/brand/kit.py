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

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, ValidationError

from portalr.brand.colour import Rgba
from portalr.brand.inventory import VERSION
from portalr.brand.tokens import DEFAULT, JSON_BYTES, BrandError, compile_kit, layered, own_bytes
from portalr.brand.validate import colour, token_faults

SVG_BYTES = 64 * 1024
PNG_BYTES = 128 * 1024
FONT_BYTES = 400 * 1024
FONTS_BYTES = 1536 * 1024
LICENCE_BYTES = 64 * 1024
FONT_FILES = 16
"""The most face files a kit may bring."""
LICENCES = frozenset({"OFL-1.1", "Apache-2.0", "MIT", "LicenseRef-commercial"})
"""The font licences a kit may name, by SPDX id; a commercial one with its own file."""

_NAME = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
_FAMILY = re.compile(r"^[A-Za-z0-9 -]{1,64}$")
_RANGE = re.compile(
    r"^U\+[0-9A-Fa-f?]{1,6}(-[0-9A-Fa-f]{1,6})?(, ?U\+[0-9A-Fa-f?]{1,6}(-[0-9A-Fa-f]{1,6})?)*$"
)
_WEIGHT = re.compile(r"^[1-9]00( [1-9]00)?$")
# A file of the kit's: in assets/ or fonts/, never `.`, `..` or hidden, as its first character is
# never a dot.
_PATH = re.compile(r"^(assets|fonts)/[A-Za-z0-9_-][A-Za-z0-9._-]{0,63}$")


_REFUSED = frozenset({"Cc", "Cf", "Co", "Cs", "Cn", "Zl", "Zp"})
"""Unicode categories a word in a page never holds: controls and formats (bidi overrides among
them), private use, surrogates, unassigned code points, and line and paragraph separators."""

_BLANKS = frozenset({"\u00a0", "\u2800", "\u3164", "\uffa0", "\u115f", "\u1160"})
"""Characters that draw as nothing but aren't a space: no-break spaces and the Hangul and Braille
fillers a name can hide behind."""


def _plain(text: str) -> str:
    """Refuse what a word in a page must never hold, and a word that draws as nothing."""
    for character in text:
        if unicodedata.category(character) in _REFUSED or character in _BLANKS:
            raise ValueError(f"{text!r} holds a control, format, blank or line-break character")
    if not text.strip():
        raise ValueError(f"{text!r} is only spaces")
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
    files: Annotated[tuple[FontFile, ...], Field(min_length=1, max_length=FONT_FILES)]
    licence: Licence


class Brand(BaseModel):
    """``brand.json``: who the kit is, in words, marks and faces."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_: str | None = Field(default=None, alias="$schema")
    """The schema an editor checks the file by; the loader reads it no further."""
    version: StrictInt
    name: Annotated[str, StringConstraints(pattern=_NAME.pattern)]
    identity: Identity
    copy_: Words = Field(default=Words(), alias="copy")
    assets: Assets
    fonts: Annotated[tuple[Font, ...], Field(max_length=FONT_FILES)] = ()


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


SVG = "{http://www.w3.org/2000/svg}"
"""The SVG namespace: every element of a mark is in it, and no attribute is in another."""

SVG_ELEMENTS = frozenset(
    f"{SVG}{local}"
    for local in [
        "svg",
        "g",
        "path",
        "rect",
        "circle",
        "ellipse",
        "line",
        "polyline",
        "polygon",
        "title",
        "desc",
        "defs",
        "linearGradient",
        "radialGradient",
        "stop",
        "clipPath",
        "mask",
    ]
)
SVG_ATTRIBUTES = frozenset(
    [
        "version",
        "viewBox",
        "width",
        "height",
        "x",
        "y",
        "x1",
        "y1",
        "x2",
        "y2",
        "cx",
        "cy",
        "r",
        "rx",
        "ry",
        "d",
        "points",
        "fill",
        "fill-rule",
        "fill-opacity",
        "clip-rule",
        "stroke",
        "stroke-width",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-opacity",
        "stroke-miterlimit",
        "stroke-dasharray",
        "opacity",
        "transform",
        "id",
        "offset",
        "stop-color",
        "stop-opacity",
        "gradientUnits",
        "gradientTransform",
        "clip-path",
        "mask",
        "role",
        "aria-label",
        "aria-hidden",
        "focusable",
        "preserveAspectRatio",
    ]
)
"""A mark's attributes, each with no namespace."""

_FRAGMENT = re.compile(r"url\(#[A-Za-z0-9_-]+\)")
_COMMENT = re.compile(rb"<!--.*?-->", re.DOTALL)
_DECLARATION = re.compile(rb"\A<\?xml\s[^?>]*\?>")


def svg_faults(name: str, data: bytes) -> list[str]:
    """An SVG's faults, by an allow-list (lattice RFC-0007).

    UTF-8 alone; no DOCTYPE, entity, CDATA or processing instruction but the XML declaration; an
    ``<svg>`` in the SVG namespace at the root and only allowed elements in it; only allowed
    attributes, in no namespace; and a ``url()`` only to a fragment of the mark itself.
    """
    if len(data) > SVG_BYTES:
        return [f"{name}: an SVG is {SVG_BYTES // 1024} KB at most"]
    if data.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")):
        return [f"{name}: an SVG is UTF-8 with no byte-order mark"]
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return [f"{name}: an SVG is UTF-8"]
    bare = _DECLARATION.sub(b"", _COMMENT.sub(b"", data).lstrip(), count=1)
    if b"<!" in bare or b"<?" in bare:
        return [f"{name}: an SVG declares nothing: no DOCTYPE, entity, CDATA or instruction"]
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        return [f"{name}: not well-formed XML ({error})"]
    if root.tag != f"{SVG}svg":
        return [f"{name}: a mark is an <svg> in the SVG namespace"]
    faults: list[str] = []
    for element in root.iter():
        if element.tag not in SVG_ELEMENTS:
            faults.append(f"{name}: <{element.tag!r}> isn't allowed in a mark")
        for attribute, value in element.attrib.items():
            if attribute not in SVG_ATTRIBUTES:
                faults.append(f"{name}: the attribute {attribute!r} isn't allowed in a mark")
            if "\\" in value:
                faults.append(f"{name}: {attribute!r} holds a backslash")
            lowered = value.lower()
            if ("url" in lowered or ":" in value) and not (
                _FRAGMENT.fullmatch(value.strip()) or attribute in {"viewBox", "d", "points"}
            ):
                faults.append(f"{name}: {attribute!r} names something outside the mark")
    return faults


def _file(kit: Path, path: str, faults: list[str], most: int) -> bytes | None:
    """A kit's file by its path in brand.json, within its cap, read only once its size is known.

    A fault if it isn't there, leaves the kit (by a linked folder), is a link itself, or is larger
    than `most`; each caller holds its files to their suffixes.
    """
    try:
        inside = (kit / path).resolve().is_relative_to(kit.resolve())
    except (OSError, RuntimeError):  # a loop of links: Python 3.12 raises, as 3.13 doesn't
        inside = False
    if not inside:
        faults.append(f"{path}: no such file in the kit")
        return None
    try:
        data = own_bytes(kit / path, most, path)
    except BrandError as error:
        faults.append(str(error))
        return None
    if data is None:
        faults.append(f"{path}: no such file in the kit")
    return data


def _asset(kit: Path, path: str, faults: list[str]) -> bytes | None:
    """A mark or the favicon: an SVG held to the allow-list, or a PNG by its signature."""
    if not path.endswith((".svg", ".png")):
        faults.append(f"{path}: a mark or a favicon is an SVG or a PNG")
        return None
    data = _file(kit, path, faults, SVG_BYTES if path.endswith(".svg") else PNG_BYTES)
    if data is None:
        return None
    if path.endswith(".svg"):
        faults.extend(svg_faults(path, data))
    elif not data.startswith(b"\x89PNG\r\n\x1a\n"):
        faults.append(f"{path}: not a PNG")
    return data


def woff2_faults(path: str, data: bytes) -> list[str]:
    """A face's faults by its WOFF2 header: its signature, its length, its tables and its size.

    The header alone: the browser's own sanitiser (OTS) checks the font itself, and is the real
    defence against a malformed one; this refuses what plainly isn't a WOFF2 file.
    """
    if len(data) < 48 or not data.startswith(b"wOF2"):
        return [f"{path}: a face is a WOFF2 file"]
    length = int.from_bytes(data[8:12], "big")
    tables = int.from_bytes(data[12:14], "big")
    sfnt = int.from_bytes(data[16:20], "big")
    if length != len(data) or tables == 0 or sfnt == 0:
        return [f"{path}: a WOFF2 header that doesn't describe its file"]
    return []


def _fonts(kit: Path, brand: Brand, files: dict[str, bytes], faults: list[str]) -> list[str]:
    """Each face's files, checked as WOFF2 within the caps, and its ``@font-face`` rules."""
    rules: list[str] = []
    total = 0
    if len(brand.fonts) > FONT_FILES or sum(len(f.files) for f in brand.fonts) > FONT_FILES:
        faults.append(f"fonts: a kit brings {FONT_FILES} face files at most")
        return rules
    for font in brand.fonts:
        if font.licence.spdx not in LICENCES:
            faults.append(f"{font.family}: its licence is one of {', '.join(sorted(LICENCES))}")
        if not font.licence.file.endswith(".txt"):
            faults.append(f"{font.licence.file}: a licence is a .txt file")
        elif font.licence.file not in files:
            licence = _file(kit, font.licence.file, faults, LICENCE_BYTES)
            if licence is not None:
                total += len(licence)
                files[font.licence.file] = licence
        for each in font.files:
            if not each.path.endswith(".woff2"):
                faults.append(f"{each.path}: a face is a .woff2 file")
                continue
            data = _file(kit, each.path, faults, FONT_BYTES)
            if data is None:
                continue
            total += len(data)
            faults.extend(woff2_faults(each.path, data))
            files[each.path] = data
            ranged = f"\n  unicode-range: {each.unicode_range};" if each.unicode_range else ""
            rules.append(
                f'@font-face {{\n  font-family: "{font.family}";\n'
                f'  src: url("{each.path}") format("woff2");\n'
                f"  font-weight: {each.weight};\n  font-style: {each.style};\n"
                f"  font-display: swap;{ranged}\n}}"
            )
    if total > FONTS_BYTES:
        faults.append(f"fonts: a kit's faces and licences are {FONTS_BYTES // 1024} KB at most")
    return rules


def _said(part: str | int) -> str:
    """A part of a path into brand.json, as a log may print it: a name as it is, else its repr."""
    text = str(part)
    return text if re.fullmatch(r"[A-Za-z0-9_$-]{1,64}", text) else repr(text)


def load(kit: Path) -> Kit:
    """Read a kit and check all of it: its brand.json, its tokens, its marks and its faces.

    Raises:
        BrandError: With every fault, one to a line, if the kit isn't one the portal can serve.
    """
    faults: list[str] = []
    if not kit.is_dir():
        raise BrandError(f"{str(kit)!r}: no such folder")
    data = own_bytes(kit / "brand.json", JSON_BYTES)
    if data is None:
        raise BrandError("brand.json: a kit has one")
    try:
        brand = Brand.model_validate(json.loads(data.decode("utf-8")))
    except RecursionError:
        raise BrandError("brand.json: nested too deep") from None
    except ValidationError as error:
        raise BrandError(
            "\n".join(
                f"brand.json: {'.'.join(map(_said, e['loc']))}: {e['msg']}" for e in error.errors()
            )
        ) from error
    except ValueError as error:  # not UTF-8, not JSON, or a number too long to read
        raise BrandError(f"brand.json: not JSON in UTF-8 ({error})") from error
    for text in (
        *brand.identity.model_dump().values(),
        *(t for t in (brand.copy_.tagline, brand.copy_.sign_in) if t is not None),
    ):
        try:
            _plain(text)
        except ValueError as error:
            faults.append(f"brand.json: {error}")
    if brand.version != VERSION:
        # One inventory so far: a later one keeps a version-1 kit working by its defaults.
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
