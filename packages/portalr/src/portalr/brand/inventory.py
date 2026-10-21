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
        " whatever the kit says, and how it eases; a placeholder's pulse and a working status's"
        " spin are loops, which reduced motion pauses (portalr ADR-0057).",
        (
            *_scale("duration", "motion.duration", "--duration", ("fast", "moderate")),
            Row("motion.duration.pulse", "--duration-pulse", "duration", loop=True),
            Row("motion.duration.spin", "--duration-spin", "duration", loop=True),
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

COMPONENTS: tuple[Group, ...] = (
    Group(
        "The focus ring: how wide it is, and how far from what it rings (inside a row, the same"
        " distance in); its colour is --focus (portalr ADR-0029).",
        _rows(
            "dimension",
            ("component.focus.width", "--focus-width"),
            ("component.focus.offset", "--focus-offset"),
        ),
    ),
    Group(
        "A button: its corners, its padding at each size, its words' weight, how far it moves"
        " down when pressed, and how its colours change (portalr ADR-0037).",
        (
            Row("component.button.radius", "--button-radius", "dimension"),
            Row("component.button.pad-x", "--button-pad-x", "dimension"),
            Row("component.button.pad-y", "--button-pad-y", "dimension"),
            Row("component.button.sm.pad-x", "--button-sm-pad-x", "dimension"),
            Row("component.button.sm.pad-y", "--button-sm-pad-y", "dimension"),
            Row("component.button.weight", "--button-weight", "fontWeight"),
            Row("component.button.press-shift", "--button-press-shift", "dimension"),
            Row("component.button.duration", "--button-duration", "duration"),
            Row("component.button.ease", "--button-ease", "cubicBezier"),
        ),
    ),
    Group(
        "A field, a select's trigger, a check, a switch and a segmented filter: their corners "
        "and padding, a check's size, and a switch's track, thumb and travel (portalr "
        "ADR-0037).",
        (
            Row("component.input.radius", "--input-radius", "dimension"),
            Row("component.input.pad-x", "--input-pad-x", "dimension"),
            Row("component.input.pad-y", "--input-pad-y", "dimension"),
            Row("component.checkbox.radius", "--checkbox-radius", "dimension"),
            Row("component.checkbox.size", "--checkbox-size", "dimension"),
            Row("component.switch.width", "--switch-width", "dimension"),
            Row("component.switch.height", "--switch-height", "dimension"),
            Row("component.switch.pad", "--switch-pad", "dimension"),
            Row("component.switch.thumb", "--switch-thumb", "dimension"),
            Row("component.switch.travel", "--switch-travel", "dimension"),
            Row("component.switch.duration", "--switch-duration", "duration"),
            Row("component.segmented.radius", "--segmented-radius", "dimension"),
            Row("component.segmented.pad", "--segmented-pad", "dimension"),
            Row("component.segmented.item-radius", "--segmented-item-radius", "dimension"),
            Row("component.segmented.item-pad-x", "--segmented-item-pad-x", "dimension"),
            Row("component.segmented.item-pad-y", "--segmented-item-pad-y", "dimension"),
        ),
    ),
    Group(
        "A card, and an empty state, which is one: corners, padding and what it casts.",
        (
            Row("component.card.radius", "--card-radius", "dimension"),
            Row("component.card.pad", "--card-pad", "dimension"),
            Row("component.card.shadow", "--card-shadow", "shadow"),
            Row("component.empty-state.pad", "--empty-state-pad", "dimension"),
        ),
    ),
    Group(
        "A dialog, and the drawer's scrim: corners, padding, width, the margin it keeps from "
        "the window's edge, what it casts, how much the scrim blurs what is behind, and how it "
        "opens (portalr ADR-0039).",
        (
            Row("component.dialog.radius", "--dialog-radius", "dimension"),
            Row("component.dialog.pad", "--dialog-pad", "dimension"),
            Row("component.dialog.width", "--dialog-width", "dimension"),
            Row("component.dialog.margin", "--dialog-margin", "dimension"),
            Row("component.dialog.shadow", "--dialog-shadow", "shadow"),
            Row("component.dialog.scrim-blur", "--dialog-scrim-blur", "dimension"),
            Row("component.dialog.duration", "--dialog-duration", "duration"),
            Row("component.dialog.enter-scale", "--dialog-enter-scale", "number"),
        ),
    ),
    Group(
        "What floats over the page, a menu, a select's choices and a chart's tooltip: corners, "
        "what it casts, its padding, an item's corners and padding, and how it opens.",
        (
            Row("component.popover.radius", "--popover-radius", "dimension"),
            Row("component.popover.shadow", "--popover-shadow", "shadow"),
            Row("component.popover.pad", "--popover-pad", "dimension"),
            Row("component.popover.item-radius", "--popover-item-radius", "dimension"),
            Row("component.popover.item-pad-x", "--popover-item-pad-x", "dimension"),
            Row("component.popover.item-pad-y", "--popover-item-pad-y", "dimension"),
            Row("component.popover.duration", "--popover-duration", "duration"),
            Row("component.popover.enter-scale", "--popover-enter-scale", "number"),
        ),
    ),
    Group(
        "A notice that floats over the page, as a new version's: where it sits, below a narrow "
        "window's bar, how far it keeps from the window's edges, its width, corners, padding and "
        "what it casts (portalr ADR-0058).",
        (
            Row("component.notice.top", "--notice-top", "dimension"),
            Row("component.notice.inset", "--notice-inset", "dimension"),
            Row("component.notice.width", "--notice-width", "dimension"),
            Row("component.notice.radius", "--notice-radius", "dimension"),
            Row("component.notice.pad", "--notice-pad", "dimension"),
            Row("component.notice.shadow", "--notice-shadow", "shadow"),
        ),
    ),
    Group(
        "The frame's navigation: a nav link's corners and padding, its count's pill, the "
        "header's triggers (the switcher, the account menu, the home link), and the drawer's "
        "width, shadow and slide.",
        (
            Row("component.nav.radius", "--nav-radius", "dimension"),
            Row("component.nav.pad-x", "--nav-pad-x", "dimension"),
            Row("component.nav.pad-y", "--nav-pad-y", "dimension"),
            Row("component.nav.count-radius", "--nav-count-radius", "dimension"),
            Row("component.header.trigger-radius", "--header-trigger-radius", "dimension"),
            Row("component.header.trigger-pad-x", "--header-trigger-pad-x", "dimension"),
            Row("component.header.trigger-pad-y", "--header-trigger-pad-y", "dimension"),
            Row("component.drawer.width", "--drawer-width", "dimension"),
            Row("component.drawer.shadow", "--drawer-shadow", "shadow"),
            Row("component.drawer.duration", "--drawer-duration", "duration"),
        ),
    ),
    Group(
        "Tabs: a tab's padding, and the width of the line under the current one.",
        (
            Row("component.tabs.pad-x", "--tabs-pad-x", "dimension"),
            Row("component.tabs.pad-y", "--tabs-pad-y", "dimension"),
            Row("component.tabs.indicator", "--tabs-indicator", "dimension"),
        ),
    ),
    Group(
        "A table: its frame's corners, and a cell's padding across; its rows' height, padding "
        "and words are the roles above, which admin's compact density sets.",
        (
            Row("component.table.radius", "--table-radius", "dimension"),
            Row("component.table.cell-pad-x", "--table-cell-pad-x", "dimension"),
        ),
    ),
    Group(
        "A status badge: its pill's corners and padding. Its shapes are status marks, which "
        "tell each status apart for every reader, and are not a kit's to change (portalr "
        "ADR-0039).",
        (
            Row("component.badge.radius", "--badge-radius", "dimension"),
            Row("component.badge.pad-y", "--badge-pad-y", "dimension"),
            Row("component.badge.pad-start", "--badge-pad-start", "dimension"),
            Row("component.badge.pad-end", "--badge-pad-end", "dimension"),
        ),
    ),
    Group(
        "What is being read and what is going: a placeholder's corners, whose pulse is a loop "
        "that reduced motion stills, and a progress bar's track and how its bar moves.",
        (
            Row("component.skeleton.radius", "--skeleton-radius", "dimension"),
            Row("component.progress.radius", "--progress-radius", "dimension"),
            Row("component.progress.height", "--progress-height", "dimension"),
            Row("component.progress.duration", "--progress-duration", "duration"),
        ),
    ),
    Group(
        "A code block: its corners, and its code's padding.",
        (
            Row("component.code-block.radius", "--code-block-radius", "dimension"),
            Row("component.code-block.pad-x", "--code-block-pad-x", "dimension"),
            Row("component.code-block.pad-y", "--code-block-pad-y", "dimension"),
        ),
    ),
    Group(
        "The chat's tool calls and questions: a tool call's corners, its summary's padding and "
        "its result's corners; a question card's corners and padding, an option's corners and "
        "padding, and a chip's corners (portalr ADR-0053).",
        (
            Row("component.tool-call.radius", "--tool-call-radius", "dimension"),
            Row("component.tool-call.pad-x", "--tool-call-pad-x", "dimension"),
            Row("component.tool-call.pad-y", "--tool-call-pad-y", "dimension"),
            Row("component.tool-call.result-radius", "--tool-call-result-radius", "dimension"),
            Row("component.question.radius", "--question-radius", "dimension"),
            Row("component.question.pad", "--question-pad", "dimension"),
            Row("component.question.option-radius", "--question-option-radius", "dimension"),
            Row("component.question.option-pad-x", "--question-option-pad-x", "dimension"),
            Row("component.question.option-pad-y", "--question-option-pad-y", "dimension"),
            Row("component.question.chip-radius", "--question-chip-radius", "dimension"),
        ),
    ),
    Group(
        "A disclosure, a part that opens and closes: its trigger's least height, so a pointer has "
        "a target, the gap after its chevron, its corners, the gap before what opens, and how fast "
        "the chevron turns (portalr ADR-0063).",
        (
            Row("component.disclosure.target", "--disclosure-target", "dimension"),
            Row("component.disclosure.gap", "--disclosure-gap", "dimension"),
            Row("component.disclosure.radius", "--disclosure-radius", "dimension"),
            Row("component.disclosure.panel-gap", "--disclosure-panel-gap", "dimension"),
            Row("component.disclosure.duration", "--disclosure-duration", "duration"),
        ),
    ),
    Group(
        "The chat: a message's bubble, its corners and the smaller corner it points from, and "
        "its padding; and the composer's corners and padding (portalr ADR-0053).",
        (
            Row("component.bubble.radius", "--bubble-radius", "dimension"),
            Row("component.bubble.tail-radius", "--bubble-tail-radius", "dimension"),
            Row("component.bubble.pad-x", "--bubble-pad-x", "dimension"),
            Row("component.bubble.pad-y", "--bubble-pad-y", "dimension"),
            Row("component.composer.radius", "--composer-radius", "dimension"),
            Row("component.composer.pad", "--composer-pad", "dimension"),
        ),
    ),
    Group(
        "An alert's corners and padding; inline code's corners and padding; and the sign-in "
        "card's corners and padding.",
        (
            Row("component.alert.radius", "--alert-radius", "dimension"),
            Row("component.alert.pad-x", "--alert-pad-x", "dimension"),
            Row("component.alert.pad-y", "--alert-pad-y", "dimension"),
            Row("component.code-inline.radius", "--code-inline-radius", "dimension"),
            Row("component.code-inline.pad-x", "--code-inline-pad-x", "dimension"),
            Row("component.code-inline.pad-y", "--code-inline-pad-y", "dimension"),
            Row("component.sign-in.radius", "--sign-in-radius", "dimension"),
            Row("component.sign-in.pad", "--sign-in-pad", "dimension"),
        ),
    ),
    Group(
        "A panel of preformatted text, a tool's result or a span's input: its padding on every "
        "side.",
        (Row("component.code-panel.pad", "--code-panel-pad", "dimension"),),
    ),
    Group(
        "Links: how far an underline sits below its words, and the size of an external link's"
        " mark and its gap; a breadcrumb's least height, so a crumb is a target 24px tall or"
        " more, and the gap between crumbs (portalr ADR-0059).",
        (
            Row("component.link.underline-offset", "--link-underline-offset", "dimension"),
            Row("component.link.mark-size", "--link-mark-size", "dimension"),
            Row("component.link.mark-gap", "--link-mark-gap", "dimension"),
            Row("component.breadcrumb.target", "--breadcrumb-target", "dimension"),
            Row("component.breadcrumb.gap", "--breadcrumb-gap", "dimension"),
        ),
    ),
    Group(
        "A list's row: its padding, the gap between what it is and its end, and between its "
        "title's line and its meta's (portalr ADR-0060).",
        (
            Row("component.list-row.pad-x", "--list-row-pad-x", "dimension"),
            Row("component.list-row.pad-y", "--list-row-pad-y", "dimension"),
            Row("component.list-row.gap", "--list-row-gap", "dimension"),
            Row("component.list-row.line-gap", "--list-row-line-gap", "dimension"),
        ),
    ),
    Group(
        "An icon button, an action named by its icon and a tooltip: its size, a target 24px or "
        "more, its corners and its icon's size; and a tooltip's padding, corners, shadow and "
        "layer, above a full view's (portalr ADR-0061).",
        (
            Row("component.icon-button.size", "--icon-button-size", "dimension"),
            Row("component.icon-button.radius", "--icon-button-radius", "dimension"),
            Row("component.icon-button.icon", "--icon-button-icon", "dimension"),
            Row("component.tooltip.pad-x", "--tooltip-pad-x", "dimension"),
            Row("component.tooltip.pad-y", "--tooltip-pad-y", "dimension"),
            Row("component.tooltip.radius", "--tooltip-radius", "dimension"),
            Row("component.tooltip.shadow", "--tooltip-shadow", "shadow"),
            Row("component.tooltip.layer", "--tooltip-layer", "number"),
        ),
    ),
)
"""Each component's tokens, defaulting to a role or a primitive (portalr ADR-0056)."""

GROUPS: tuple[Group, ...] = (*PRIMITIVES, *ROLES, *COMPONENTS)

ROWS: dict[str, Row] = {row.path: row for group in GROUPS for row in group.rows}
"""Every token, by its path."""
