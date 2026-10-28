"""What a batch of an app's commands does, in words: a line, and each (native files ADR-0020).

A proposal by an agent's commands is reviewed before it is accepted, and its reviewer reads first
what it does, then each command with its arguments. The words are made here, from the batch alone,
so one table serves every surface that says them. A craft whose commands are named in `CRAFTS`
says them in its own verbs ("Adds 6 slides: Title, Itinerary, …"); any other, or a command no
table names, is said by its name, with how many times the batch runs it ("Runs 3 commands: …").
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel, ConfigDict, JsonValue

from artifactr.files.app import AppCommand

MOST_ITEMS: Final = 200
"""The most commands a description lists one by one; `total` counts them all."""

LONGEST: Final = 1_000
"""The most characters of a string argument a listed command keeps, the rest cut with `…`."""

QUOTED: Final = 80
"""The most characters of an argument a command's words quote."""

TIMES: Final = "\N{MULTIPLICATION SIGN}"
"""Between a command's name and how many times a batch runs it."""

NAMED: Final = 5
"""The most things a description's line names, such as the titles of the slides it adds."""


class Change(BaseModel):
    """One command of a batch: what it does, in words, and the command, its long strings cut."""

    model_config = ConfigDict(frozen=True)

    text: str
    name: str
    args: dict[str, JsonValue]


class Described(BaseModel):
    """What a batch of commands does: a line, its first `MOST_ITEMS` commands, and how many."""

    model_config = ConfigDict(frozen=True)

    summary: str
    items: list[Change]
    total: int


@dataclass(frozen=True)
class Says:
    """How a craft says one of its commands: a verb and what it acts on, one and many.

    `named` is the argument that names each one, quoted in its words and named in the line;
    `counts` the string argument whose characters are counted in the line in place of commands.
    """

    verb: str
    one: str
    many: str
    named: str = ""
    counts: str = ""


def _says(*lines: str) -> Mapping[str, Says]:
    """A craft's table, a line each: `command|verb|one|many|named|counts`, the last two optional."""
    table: dict[str, Says] = {}
    for line in lines:
        name, verb, one, many, *rest = line.split("|")
        named, counts = (*rest, "", "")[:2]
        table[name] = Says(verb, one, many, named, counts)
    return table


_HEADING = "Makes|a heading|headings"
_PAGE_BREAK = "Inserts|a page break|page breaks"

CRAFTS: Final[Mapping[str, Mapping[str, Says]]] = {
    # WordCraft 0.11's commands, as its `list_commands` lists them: it types, as a person does.
    "wordcraft": _says(
        "text.insert|Types|a character|characters|text|text",
        "text.newParagraph|Starts|a new paragraph|new paragraphs",
        f"para.heading1|{_HEADING}",
        f"para.heading2|{_HEADING}",
        f"para.heading3|{_HEADING}",
        "para.style|Applies|a style|styles|style",
        "para.bullets|Makes|a bulleted list|bulleted lists",
        "para.numbering|Makes|a numbered list|numbered lists",
        "insert.table|Inserts|a table|tables",
        "insert.picture|Inserts|a picture|pictures|alt",
        "insert.textBox|Inserts|a text box|text boxes|text",
        "insert.shape|Inserts|a shape|shapes|kind",
        "insert.link|Inserts|a link|links|url",
        "insert.coverPage|Adds|a cover page|cover pages|title",
        "insert.header|Adds|a header|headers|text",
        "insert.footer|Adds|a footer|footers|text",
        f"insert.pageBreak|{_PAGE_BREAK}",
        f"text.pageBreak|{_PAGE_BREAK}",
        "review.newComment|Adds|a comment|comments|text",
    ),
    # DeckCraft 0.7's, as its `list_commands` lists them.
    "deckcraft": _says(
        "slide.new|Adds|a slide|slides|title",
        "slide.duplicate|Duplicates|a slide|slides",
        "slide.delete|Deletes|a slide|slides",
        "slide.move|Moves|a slide|slides",
        "slide.layout|Changes the layout of|a slide|slides|layout",
        "slide.notes|Writes notes on|a slide|slides|text",
        "slide.fromOutline|Adds slides from|an outline|outlines",
        "text.set|Sets|a text|texts|text",
        "text.insert|Types|a character|characters|text|text",
        "insert.textBox|Inserts|a text box|text boxes|text",
        "insert.table|Inserts|a table|tables",
        "insert.chart|Inserts|a chart|charts|type",
        "insert.picture|Inserts|a picture|pictures|name",
        "insert.smartArt|Inserts|a diagram|diagrams|kind",
        "shape.insert|Inserts|a shape|shapes|text",
        "design.theme|Applies|a theme|themes|name",
        "transition.set|Sets|a transition|transitions|kind",
        "comment.add|Adds|a comment|comments|text",
    ),
}
"""Each craft's commands worth saying in its own words, by the craft's name."""


def describe(app: str | None, commands: Sequence[AppCommand]) -> Described:
    """What a batch of `app`'s commands does: a line, and each command, in words.

    Args:
        app: The app the batch is for, as provenance records it, such as `wordcraft`.
        commands: The batch, as it was applied.
    """
    table = CRAFTS.get(app or "", {})
    items = [_item(table.get(command.name), command) for command in commands[:MOST_ITEMS]]
    return Described(summary=_summary(table, commands), items=items, total=len(commands))


def _item(says: Says | None, command: AppCommand) -> Change:
    args = {key: _cut(value) for key, value in command.args.items()}
    if says is None:
        quoted = next((value for value in command.args.values() if isinstance(value, str)), None)
        text = command.name if quoted is None else f"{command.name}: {_quote(quoted)}"
    elif says.counts:
        text = f"{says.verb} {_quote(command.args.get(says.counts))}"
    else:
        name = command.args.get(says.named) if says.named else None
        text = f"{says.verb} {says.one}" + (f": {_quote(name)}" if isinstance(name, str) else "")
    return Change(text=text, name=command.name, args=args)


def _summary(table: Mapping[str, Says], commands: Sequence[AppCommand]) -> str:
    if not commands:
        return "Changes nothing."
    counted: dict[tuple[str, str, str], int] = {}
    names: dict[tuple[str, str, str], list[str]] = {}
    others = 0
    for command in commands:
        says = table.get(command.name)
        if says is None:
            others += 1
            continue
        key = (says.verb, says.one, says.many)
        value = command.args.get(says.counts or says.named)
        size = len(value) if says.counts and isinstance(value, str) else 1
        counted[key] = counted.get(key, 0) + size
        if says.named and not says.counts and isinstance(value, str) and value.strip():
            names.setdefault(key, []).append(_short(value.strip()))
    if not counted:
        return _ran(commands)
    parts = [_counted(verb, one, many, n) for (verb, one, many), n in counted.items()]
    none: list[str] = []
    named = next(iter(names.values()), none)
    if len(parts) == 1 and named:
        parts[0] += f": {_listed(named)}"
    if others:
        parts.append(f"runs {_count(others, 'another command', 'other commands')}")
    return f"{_joined([parts[0][0].upper() + parts[0][1:], *parts[1:]])}."


def _ran(commands: Sequence[AppCommand]) -> str:
    """A batch no table says, by its commands' names, each with how many times it runs."""
    tally = Counter(command.name for command in commands)
    shown = [name if n == 1 else f"{name} {TIMES}{n}" for name, n in tally.most_common(NAMED)]
    end = ", …" if len(tally) > NAMED else "."
    return f"Runs {_count(len(commands), 'a command', 'commands')}: {', '.join(shown)}{end}"


def _counted(verb: str, one: str, many: str, n: int) -> str:
    return f"{verb.lower()} {_count(n, one, many)}"


def _count(n: int, one: str, many: str) -> str:
    return one if n == 1 else f"{n:,} {many}"


def _listed(names: Sequence[str]) -> str:
    shown = list(names[:NAMED])
    if len(names) > NAMED:
        shown.append(f"{len(names) - NAMED} more")
    return _joined(shown)


def _joined(parts: Sequence[str]) -> str:
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"


def _short(text: str) -> str:
    line = " ".join(text.split())
    return line if len(line) <= QUOTED else f"{line[: QUOTED - 1]}…"


def _quote(value: JsonValue) -> str:
    return f"“{_short(value)}”" if isinstance(value, str) else "nothing"


def _cut(value: JsonValue) -> JsonValue:
    """A value as listed: each string longer than `LONGEST` cut, all the way down."""
    match value:
        case str() if len(value) > LONGEST:
            return f"{value[: LONGEST - 1]}…"
        case list():
            return [_cut(item) for item in value]
        case dict():
            return {key: _cut(item) for key, item in value.items()}
        case _:
            return value
