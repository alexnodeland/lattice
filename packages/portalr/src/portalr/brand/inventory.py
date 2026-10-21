"""The token inventory: each token a kit may set, its DTCG path, its type and its property.

A lookup table, not a naming rule (lattice RFC-0007): a path with no row is no token. The rows are
in the order the stylesheet declares them, in groups, each with the note the stylesheet carries
above it. The inventory's version is :data:`VERSION`; a row added later comes with a default in
the default kit and a bump, and a row renamed or removed is a major one.
"""

from dataclasses import dataclass
from typing import Literal

VERSION = 1
"""The inventory's version, which a kit's ``brand.json`` names (lattice RFC-0007)."""

Type = Literal[
    "color", "dimension", "duration", "cubicBezier", "number", "fontWeight", "fontFamily", "shadow"
]


@dataclass(frozen=True)
class Row:
    """One token: where a kit sets it, what it is, and the custom property it becomes."""

    path: str
    prop: str
    type: Type
    loop: bool = False
    """A loop's duration, which reduced motion pauses, rather than one that it makes instant."""


@dataclass(frozen=True)
class Group:
    """Tokens declared together, under one note."""

    note: str
    rows: tuple[Row, ...]


def _rows(type_: Type, *pairs: tuple[str, str]) -> tuple[Row, ...]:
    return tuple(Row(path, prop, type_) for path, prop in pairs)


def _scale(type_: Type, path: str, prop: str, steps: tuple[str, ...]) -> tuple[Row, ...]:
    return tuple(Row(f"{path}.{step}", f"{prop}-{step}", type_) for step in steps)


PRIMITIVES: tuple[Group, ...] = (
    Group(
        "The inks: the mark's three plates, and the overprint where they cross (lattice ADR-0014).",
        _rows(
            "color",
            ("color.ink.portalr.cyan", "--portalr-cyan"),
            ("color.ink.portalr.magenta", "--portalr-magenta"),
            ("color.ink.portalr.yellow", "--portalr-yellow"),
            ("color.ink.portalr.violet", "--portalr-violet"),
        ),
    ),
    Group(
        "Space: steps of a quarter rem, and a hairline and a half step below them.",
        _scale("dimension", "space", "--space", ("px", "half", "1", "1-5", "2", "3", "4", "6")),
    ),
    Group(
        "Corners, from square to round: each a component's radius defaults to one of these.",
        (
            *_scale("dimension", "radius", "--radius", ("0", "1", "2", "3", "4", "5", "6")),
            Row("radius.full", "--radius-full", "dimension"),
        ),
    ),
    Group(
        "Type: the faces, the sizes, the weights (none past 600, ADR-0039) and the leading.",
        (
            Row("font.family.sans", "--font-family-sans", "fontFamily"),
            Row("font.family.mono", "--font-family-mono", "fontFamily"),
            *_scale(
                "dimension", "font.size", "--font-size", ("xs", "sm", "base", "lg", "xl", "2xl")
            ),
            *_scale("fontWeight", "font.weight", "--weight", ("normal", "medium", "semibold")),
            *_scale("number", "font.leading", "--leading", ("tight", "snug", "normal", "relaxed")),
        ),
    ),
    Group(
        "Edges: a hairline, and the focus ring's width.",
        _scale("dimension", "border.width", "--border-width", ("1", "2")),
    ),
    Group(
        "Elevation: a card's, a menu's or a tooltip's, and a dialog's or a drawer's (ADR-0039),"
        " each cast in --shadow-color.",
        _scale("shadow", "shadow", "--shadow", ("1", "2", "3")),
    ),
    Group(
        "Motion: how long a change takes, scaled by --motion-scale, which reduced motion makes 0"
        " whatever the kit says, and how it eases; a placeholder's pulse is a loop, which reduced"
        " motion pauses (portalr ADR-0057).",
        (
            *_scale("duration", "motion.duration", "--duration", ("fast", "moderate")),
            Row("motion.duration.pulse", "--duration-pulse", "duration", loop=True),
            *_scale("cubicBezier", "motion.ease", "--ease", ("in", "out", "in-out", "pulse")),
        ),
    ),
)

ROLES: tuple[Group, ...] = (
    Group(
        "The roles the components use: the paper, a surface on it, the text, the quiet text, a"
        " line, and the working colour and what is written on it.",
        _rows(
            "color",
            ("color.paper", "--paper"),
            ("color.surface", "--surface"),
            ("color.fg", "--fg"),
            ("color.muted", "--muted"),
            ("color.line", "--line"),
            ("color.accent", "--accent"),
            ("color.on-accent", "--on-accent"),
        ),
    ),
    Group(
        "The focus ring: the brand's violet in both schemes, lighter in the dark, never another"
        " ink. A control's boundary: 3:1 or more on every surface, as WCAG asks of one.",
        _rows("color", ("color.focus", "--focus"), ("color.edge", "--edge")),
    ),
    Group(
        "Status, as marks and never as text: a rose red for what failed, was dead-lettered or is"
        " an error, and a gold for what is retrying or a warning; what succeeded stays neutral."
        " Each is 3:1 or more on the paper and the surface, the pair differ in lightness as well"
        " as hue, and each is 20 or more, to CIEDE2000, from the other and from the chart accent,"
        " to every reader (portalr ADR-0039). What a destructive action is in: the same red.",
        _rows(
            "color",
            ("color.status.failed", "--status-failed"),
            ("color.status.warn", "--status-warn"),
            ("color.danger", "--danger"),
            ("color.on-danger", "--on-danger"),
        ),
    ),
    Group(
        "A chart's series, in this order and no more: tints of the brand violet, then one accent,"
        " a teal, as marks and never as text (ADR-0021, ADR-0036). Each is 3:1 or more on the"
        " paper and the surface, and the pairs are 20 or more apart, to CIEDE2000, to every"
        " reader. A hue is never a series' only cue.",
        _scale("color", "color.chart", "--chart", ("1", "2", "3")),
    ),
    Group(
        "A log line's eight ANSI colours, as text: 4.5:1 or more on the paper and the surface in"
        " each scheme (portalr ADR-0031).",
        _scale("color", "color.ansi", "--ansi", tuple(str(n) for n in range(8))),
    ),
    Group(
        "Code's colours, which highlighting's theme names: the working colour for keywords, a"
        " log line's colours for the rest, the quiet ink for comments. Each is 4.5:1 or more on"
        " the paper and the surface (portalr ADR-0044).",
        (
            Row("color.code.foreground", "--code-foreground", "color"),
            Row("color.code.background", "--code-background", "color"),
            *_scale(
                "color",
                "color.code.token",
                "--code-token",
                (
                    "keyword",
                    "link",
                    "string",
                    "string-expression",
                    "function",
                    "constant",
                    "parameter",
                    "punctuation",
                    "comment",
                ),
            ),
        ),
    ),
    Group(
        "How wide a page's content is, at most; a table row's least height, its padding and its"
        " words (admin's compact density changes the last three, ADR-0039).",
        _rows(
            "dimension",
            ("size.page-width", "--page-width"),
            ("size.row-height", "--row-height"),
            ("size.row-pad", "--row-pad"),
            ("size.table-text", "--table-text"),
        ),
    ),
    Group(
        "Behind a drawer or a dialog; and what a raised thing casts, faint in light and, to be"
        " seen on the dark paper, black and heavier in dark.",
        _rows("color", ("color.scrim", "--scrim"), ("color.shadow", "--shadow-color")),
    ),
)

COMPONENTS: tuple[Group, ...] = ()
"""Each component's tokens, defaulting to a role or a primitive (portalr ADR-0056)."""

GROUPS: tuple[Group, ...] = (*PRIMITIVES, *ROLES, *COMPONENTS)

ROWS: dict[str, Row] = {row.path: row for group in GROUPS for row in group.rows}
"""Every token, by its path."""
