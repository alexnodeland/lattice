"""What a kit's tokens must hold, beyond their grammar (lattice RFC-0007, portalr ADR-0056/0057).

Contrast by the pair manifest (``pairs.json``) in both schemes, with the colours base.css mixes
mixed the same way and a colour with alpha composited over the paper; the chart's and the status
colours told apart to every reader; motion's guard rails; and the accessibility floors. Each
fault is a line a person can act on.
"""

import json
from collections.abc import Mapping
from itertools import combinations
from pathlib import Path
from typing import cast

from portalr.brand.colour import DEFICIENCIES, Rgba, contrast, distance, mix
from portalr.brand.inventory import ROWS, Row
from portalr.brand.tokens import resolved

PAIRS = Path(__file__).parent / "pairs.json"

APART = 20.0
"""The least CIEDE2000 distance between two marks a reader tells apart (portalr ADR-0036)."""

ROOT_PX = 16.0
"""A rem, in pixels, as the UIs set it."""

BY_PROP: dict[str, Row] = {row.prop.removeprefix("--"): row for row in ROWS.values()}

_DERIVED = {
    "danger-wash": ("danger", 0.12, "transparent"),
    "wash": ("accent", 0.10, "paper"),
    "selection": ("accent", 0.22, "paper"),
    "accent-hover": ("accent", 0.88, "on-accent"),
    "danger-hover": ("danger", 0.88, "on-danger"),
}
"""The colours base.css mixes from the kit's: each the first at a share, with the second."""

_MARKS = (("chart-1", "chart-2", "chart-3"), ("status-failed", "status-warn", "chart-3"))
"""Sets whose members must be told apart to every reader: the series, and the statuses."""


def _rgba(value: object) -> Rgba:
    if isinstance(value, str):
        return Rgba.hex(value)
    colour = cast("dict[str, object]", value)
    alpha = colour.get("alpha", 1)
    return Rgba.hex(str(colour["hex"]), float(alpha) if isinstance(alpha, int | float) else 1.0)


def colour(name: str, tokens: Mapping[str, object], backdrop: str = "paper") -> Rgba:
    """A role's colour as the page draws it: mixed as base.css mixes it, over its backdrop."""
    if name in _DERIVED:
        one, share, other = _DERIVED[name]
        drawn = mix(colour(one, tokens, backdrop), share, _clear(other, tokens))
    else:
        drawn = _rgba(resolved(BY_PROP[name].path, tokens))
    if drawn.a < 1:
        drawn = drawn.over(colour(backdrop, tokens))
    return drawn


def _clear(name: str, tokens: Mapping[str, object]) -> Rgba:
    """A mix's second colour as base.css names it, clear where it is `transparent`."""
    return Rgba(0, 0, 0, 0) if name == "transparent" else colour(name, tokens)


def _px(path: str, tokens: Mapping[str, object]) -> float:
    measure = cast("dict[str, object]", resolved(path, tokens))
    value = float(cast("float", measure["value"]))
    return value * ROOT_PX if measure["unit"] == "rem" else value


def _ms(path: str, tokens: Mapping[str, object]) -> float:
    return float(cast("float", cast("dict[str, object]", resolved(path, tokens))["value"]))


def _number(path: str, tokens: Mapping[str, object]) -> float:
    return float(cast("float", resolved(path, tokens)))


def contrast_faults(schemes: Mapping[str, Mapping[str, object]]) -> list[str]:
    """Each pair of the manifest under its floor, in each scheme."""
    pairs = json.loads(PAIRS.read_text())["pairs"]
    faults: list[str] = []
    for scheme, tokens in schemes.items():
        for pair in pairs:
            backdrop = pair.get("backdrop", "paper")
            ratio = contrast(
                colour(pair["fg"], tokens, backdrop), colour(pair["bg"], tokens, backdrop)
            )
            if ratio < pair["min"]:
                faults.append(
                    f"{scheme}: --{pair['fg']} on --{pair['bg']} is {ratio:.2f}:1, under "
                    f"{pair['min']}:1 ({pair['why']})"
                )
    return faults


def distance_faults(schemes: Mapping[str, Mapping[str, object]]) -> list[str]:
    """Each two marks closer than `APART`, to a reader who sees every colour or one who doesn't."""
    faults: list[str] = []
    for scheme, tokens in schemes.items():
        for group in _MARKS:
            for one, other in combinations(group, 2):
                for deficiency in (None, *DEFICIENCIES):
                    apart = distance(colour(one, tokens), colour(other, tokens), deficiency)
                    if apart < APART:
                        reader = deficiency or "every reader"
                        faults.append(
                            f"{scheme}: --{one} and --{other} are {apart:.1f} apart to "
                            f"{reader}, under {APART:.0f}"
                        )
    return faults


def motion_faults(tokens: Mapping[str, object]) -> list[str]:
    """Motion's guard rails (portalr ADR-0057)."""
    faults: list[str] = []
    for row in ROWS.values():
        if row.type == "duration" and not row.loop and _ms(row.path, tokens) > 600:
            faults.append(f"{row.path}: a change takes 600ms at most")
        if row.type == "duration" and row.loop and _ms(row.path, tokens) < 333:
            faults.append(f"{row.path}: a loop is slower than three times a second")
        if row.type == "cubicBezier":
            curve = cast("list[float]", resolved(row.path, tokens))
            if not (-0.1 <= curve[1] <= 1.1 and -0.1 <= curve[3] <= 1.1):
                faults.append(f"{row.path}: an easing overshoots by a tenth at most")
    faults.extend(
        f"{path}: an entry's scale starts from 0.9 to 1"
        for path in ("component.dialog.enter-scale", "component.popover.enter-scale")
        if not 0.9 <= _number(path, tokens) <= 1
    )
    if _px("component.button.press-shift", tokens) > 24:
        faults.append("component.button.press-shift: a press moves 24px at most")
    return faults


FLOORS: tuple[tuple[str, float, str], ...] = (
    ("component.focus.width", 2, "a focus ring is 2px wide or more"),
    ("component.focus.offset", 2, "a focus ring stands 2px off or more"),
    ("component.icon-button.size", 24, "an icon button is a target 24px or more"),
    ("component.breadcrumb.target", 24, "a crumb is a target 24px or more"),
    ("size.row-height", 24, "a row is a target 24px or more"),
    ("font.size.sm", 14, "body text is 14px or more"),
)


def floor_faults(tokens: Mapping[str, object]) -> list[str]:
    """The accessibility floors a kit can't go under (lattice RFC-0007)."""
    faults = [f"{path}: {said}" for path, least, said in FLOORS if _px(path, tokens) < least]
    if _number("font.leading.normal", tokens) < 1.4:
        faults.append("font.leading.normal: body text's leading is 1.4 or more")
    return faults


def token_faults(light: Mapping[str, object], dark: Mapping[str, object]) -> list[str]:
    """Every fault in a kit's tokens, once they read by their grammar."""
    schemes = {"light": light, "dark": dark}
    return [
        *contrast_faults(schemes),
        *distance_faults(schemes),
        *motion_faults(light),
        *motion_faults(dark),
        *(f"light: {fault}" for fault in floor_faults(light)),
        *(f"dark: {fault}" for fault in floor_faults(dark)),
    ]
