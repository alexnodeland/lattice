"""A kit's DTCG tokens, read, layered and written as the custom properties the UIs read.

A kit is a delta over the default kit (lattice RFC-0007): the default's tokens, then the kit's
``tokens.light.json``, then, for dark, its ``tokens.dark.json`` laid over the light result. Each
token is parsed by its type's grammar into a value this module prints, so no text a kit wrote
reaches the stylesheet; an alias, ``{path}``, becomes the custom property of the token it names.
"""

import json
import math
import re
import textwrap
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import cast

from portalr.brand.inventory import GROUPS, ROWS, Row, Type

DEFAULT = Path(__file__).parent / "default"
"""The default kit: portalr's own look."""

MAX_ALIAS_DEPTH = 8
"""How many aliases a token may go through before it reaches a value (lattice RFC-0007)."""

_ALIAS = re.compile(r"^\{([a-z0-9-]+(?:\.[a-z0-9-]+)*)\}$")
_HEX = re.compile(r"^#[0-9a-f]{6}$")
_FAMILY = re.compile(r"^[A-Za-z0-9 -]+$")
_GENERIC = frozenset(
    {"ui-sans-serif", "system-ui", "sans-serif", "ui-serif", "serif", "ui-monospace", "monospace"}
)
_UNITS = {"dimension": ("rem", "px"), "duration": ("ms",)}


class BrandError(ValueError):
    """A kit that can't be read: every fault in it, one to a line."""


def _mapping(value: object) -> dict[str, object] | None:
    """`value` as a JSON object, or None."""
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def _list(value: object) -> list[object] | None:
    """`value` as a JSON array, or None."""
    return cast("list[object]", value) if isinstance(value, list) else None


def _flatten(tree: dict[str, object], at: str) -> Iterator[tuple[str, object]]:
    for key, node in tree.items():
        if key.startswith("$"):
            continue
        path = f"{at}.{key}" if at else key
        group = _mapping(node)
        if group is None:
            raise BrandError(f"{path}: a token is an object with a $value")
        if "$value" in group:
            yield path, group["$value"]
        else:
            yield from _flatten(group, path)


def read(path: Path) -> dict[str, object]:
    """A DTCG file's tokens, by path, each still as the kit wrote it; a missing file has none."""
    if not path.exists():
        return {}
    tree = _mapping(json.loads(path.read_text()))
    if tree is None:
        raise BrandError(f"{path.name}: a token file is an object")
    tokens = dict(_flatten(tree, ""))
    if unknown := sorted(set(tokens) - set(ROWS)):
        raise BrandError("\n".join(f"{name}: no token has this path" for name in unknown))
    return tokens


def _number(value: object, path: str) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise BrandError(f"{path}: {value!r} is not a number")
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def _measure(value: object, path: str, type_: str) -> str:
    measure = _mapping(value)
    if measure is None or set(measure) != {"value", "unit"}:
        raise BrandError(f"{path}: a {type_} is {{value, unit}}")
    unit = measure["unit"]
    if not isinstance(unit, str) or unit not in _UNITS[type_]:
        raise BrandError(f"{path}: a {type_} is in {' or '.join(_UNITS[type_])}")
    number = _number(measure["value"], path)
    return number if number == "0" and type_ == "dimension" else f"{number}{unit}"


def _color(value: object, path: str) -> str:
    if isinstance(value, str) and _HEX.match(value):
        return value
    color = _mapping(value)
    if color is not None and color.get("colorSpace") == "srgb" and "hex" in color:
        hex_, alpha = color["hex"], color.get("alpha", 1)
        if not (isinstance(hex_, str) and _HEX.match(hex_)):
            raise BrandError(f"{path}: {hex_!r} is not a colour in #rrggbb")
        if isinstance(alpha, bool) or not isinstance(alpha, int | float) or not 0 <= alpha <= 1:
            raise BrandError(f"{path}: an alpha is from 0 to 1")
        if alpha == 1:
            return hex_
        red, green, blue = (int(hex_[at : at + 2], 16) for at in (1, 3, 5))
        return f"rgb({red} {green} {blue} / {_number(round(alpha * 100, 4), path)}%)"
    raise BrandError(f"{path}: a colour is #rrggbb in lower case, or an srgb object with its hex")


def _family(value: object, path: str) -> str:
    names = [name for name in _list(value) or [] if isinstance(name, str)]
    if not names or names != _list(value):
        raise BrandError(f"{path}: a font family is a list of names")
    if names[-1] not in _GENERIC:
        raise BrandError(f"{path}: a font family ends in a generic family, such as sans-serif")
    for name in names:
        if not _FAMILY.match(name):
            raise BrandError(f"{path}: {name!r} has more than letters, digits, spaces and hyphens")
    return ", ".join(name if name in _GENERIC else f'"{name}"' for name in names)


def _shadow(value: object, path: str, resolve: Callable[[object, Type], str]) -> str:
    printed: list[str] = []
    for each in _list(value) or [value]:
        layer = _mapping(each)
        keys = {"color", "offsetX", "offsetY", "blur", "spread"}
        if layer is None or not keys - {"spread"} <= set(layer) <= keys:
            raise BrandError(f"{path}: a shadow is {{color, offsetX, offsetY, blur, spread}}")
        parts = [_measure(layer[key], path, "dimension") for key in ("offsetX", "offsetY", "blur")]
        if "spread" in layer and (spread := _measure(layer["spread"], path, "dimension")) != "0":
            parts.append(spread)
        parts.append(resolve(layer["color"], "color"))
        printed.append(" ".join(parts))
    return ", ".join(printed)


def _ease(value: object, path: str) -> str:
    numbers = _list(value)
    if numbers is None or len(numbers) != 4:
        raise BrandError(f"{path}: an easing is four numbers")
    x1, y1, x2, y2 = (_number(number, path) for number in numbers)
    if not (0 <= float(x1) <= 1 and 0 <= float(x2) <= 1):
        raise BrandError(f"{path}: an easing's x values are from 0 to 1")
    return f"cubic-bezier({x1}, {y1}, {x2}, {y2})"


def _printed(row: Row, value: object, tokens: Mapping[str, object], depth: int = 0) -> str:
    """A token's value as the stylesheet declares it: an alias as its token's custom property."""

    def alias(target: str, type_: Type) -> str:
        named = ROWS.get(target)
        if named is None:
            raise BrandError(f"{row.path}: {{{target}}} names no token")
        if named.type != type_:
            raise BrandError(f"{row.path}: {{{target}}} is a {named.type}, not a {type_}")
        if depth >= MAX_ALIAS_DEPTH:
            raise BrandError(f"{row.path}: more than {MAX_ALIAS_DEPTH} aliases deep, or a cycle")
        # Followed to its end, so a cycle or a bad value behind an alias is still refused.
        _printed(named, tokens[target], tokens, depth + 1)
        return f"var({named.prop})"

    def resolve(part: object, type_: Type) -> str:
        if isinstance(part, str) and (match := _ALIAS.match(part)):
            return alias(match[1], type_)
        return _printed(Row(row.path, row.prop, type_), part, tokens, depth)

    if isinstance(value, str) and (match := _ALIAS.match(value)):
        return alias(match[1], row.type)
    match row.type:
        case "color":
            return _color(value, row.path)
        case "duration" if not row.loop:
            # Every change's duration is scaled by motion's scale, which reduced motion makes 0.
            return f"calc({_measure(value, row.path, row.type)} * var(--motion-scale))"
        case "dimension" | "duration":
            return _measure(value, row.path, row.type)
        case "number":
            return _number(value, row.path)
        case "fontWeight":
            weight = _number(value, row.path)
            if weight not in {str(step) for step in range(100, 1000, 100)}:
                raise BrandError(f"{row.path}: a weight is 100 to 900, in hundreds")
            return weight
        case "fontFamily":
            return _family(value, row.path)
        case "cubicBezier":
            return _ease(value, row.path)
        case "shadow":  # pragma: no branch, the last of the types
            return _shadow(value, row.path, resolve)


def _note(text: str) -> list[str]:
    lines = textwrap.wrap(text, 94)
    if len(lines) == 1:
        return [f"  /* {lines[0]} */"]
    return ["  /*", *(f"   * {line}" for line in lines), "   */"]


def compile_kit(kit: Path = DEFAULT, *, default: Path = DEFAULT) -> str:
    """A kit's tokens as a stylesheet: each in `:root`, a colour that differs as a pair."""
    light = read(default / "tokens.light.json")
    dark = {**light, **read(default / "tokens.dark.json")}
    if kit != default:
        light = {**light, **read(kit / "tokens.light.json")}
        dark = {**dark, **read(kit / "tokens.light.json"), **read(kit / "tokens.dark.json")}
    faults: list[str] = []
    lines = [
        "/*",
        " * Generated from portalr's default brand kit (src/portalr/brand/default) by `moon run",
        " * portalr:brand`: edit the kit, not this file (lattice RFC-0007, portalr ADR-0056).",
        " * What a kit can't set, and what is mixed from these, is in base.css.",
        " */",
        "",
        ":root {",
    ]
    differs: list[str] = []
    for group in GROUPS:
        lines.extend(_note(group.note))
        for row in group.rows:
            if row.path not in light:
                faults.append(f"{row.path}: the default kit has no value for it")
                continue
            try:
                lit, unlit = (
                    _printed(row, light[row.path], light),
                    _printed(row, dark[row.path], dark),
                )
            except BrandError as error:
                faults.append(str(error))
                continue
            if lit == unlit:
                lines.append(f"  {row.prop}: {lit};")
            elif row.type == "color":
                lines.append(f"  {row.prop}: light-dark({lit}, {unlit});")
            else:
                lines.append(f"  {row.prop}: {lit};")
                differs.append(f"  {row.prop}: {unlit};")
        lines.append("")
    if faults:
        raise BrandError("\n".join(faults))
    lines[-1] = "}"
    if differs:
        lines += ["", ':root[data-theme="dark"] {', *differs, "}", ""]
        lines += ["@media (prefers-color-scheme: dark) {", '  :root:not([data-theme="light"]) {']
        lines += [f"  {line}" for line in differs] + ["  }", "}"]
    return "\n".join(lines) + "\n"
