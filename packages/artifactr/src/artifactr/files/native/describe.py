"""What a batch of an app's commands does, in words: a line, and each (native files ADR-0020).

A proposal by an agent's commands is reviewed before it is accepted, and its reviewer reads first
what it does, then each command with its arguments. The words are made here, from the batch alone,
so one table serves every surface that says them. A craft whose commands are named in `CRAFTS`
says them in its own verbs ("Adds 6 slides: Title, Itinerary, …"); any other, or a command no
table names, is said by its name, with how many times the batch runs it ("Runs 3 commands: …").
"""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
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

QUOTABLE: Final = ("text", "title", "name", "label")
"""The arguments a command no table names is quoted by, the first it has: words, never a path
or a token."""

MASKED: Final = frozenset({"path"})
"""The arguments listed as `…`: a path on the server, which says nothing to a reviewer."""

NAMED: Final = 5
"""The most things a description's line names, such as the titles of the slides it adds."""


class CommandChange(BaseModel):
    """One command of a batch: what it does, in words, and the command, its long strings cut."""

    model_config = ConfigDict(frozen=True)

    text: str
    name: str
    args: dict[str, JsonValue]
    pages: list[int] = []
    """The pages of the proposed file it changes, from 1, where its craft can name them."""


class ProposalDescription(BaseModel):
    """What a batch of commands does: a line, its first `MOST_ITEMS` commands, and how many."""

    model_config = ConfigDict(frozen=True)

    summary: str
    items: list[CommandChange]
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
    # GridCraft 0.8's, as its `commands --json` lists them.
    "gridcraft": _says(
        "cell.set|Enters|a cell|cells|input",
        "range.setValues|Sets the values of|a range|ranges|range",
        "home.insertRows|Inserts|a row|rows",
        "home.insertColumns|Inserts|a column|columns",
        "home.deleteRows|Deletes|a row|rows",
        "home.deleteColumns|Deletes|a column|columns",
        "home.insertSheet|Adds|a sheet|sheets|name",
        "home.deleteSheet|Deletes|a sheet|sheets|sheet",
        "sheet.rename|Renames|a sheet|sheets|name",
        "chart.set|Changes|a chart|charts|title",
        "chart.delete|Deletes|a chart|charts",
        "insert.textBox|Inserts|a text box|text boxes|text",
        "shape.setText|Sets the text of|a text box|text boxes|text",
        "data.removeDuplicates|Removes duplicates from|a range|ranges|range",
    ),
    # PdfCraft 0.8's, as its `tools` names the commands they run.
    "pdfcraft": _says(
        "page.rotate|Rotates|a set of pages|sets of pages|pages",
        "page.delete|Deletes|a set of pages|sets of pages|pages",
        "page.insert|Inserts pages from|a file|files",
        "page.insert_blank|Inserts|a blank page|blank pages",
        "page.duplicate|Duplicates|a set of pages|sets of pages|pages",
        "page.replace|Replaces|a set of pages|sets of pages|pages",
        "edit.text|Adds|a text|texts|text",
        "edit.image|Adds|an image|images",
        "edit.link|Adds|a link|links|url",
        "comment.stamp|Adds|a stamp|stamps|name",
        "protect.password|Protects|the file|files",
        "protect.remove|Removes the protection of|the file|files",
    ),
    # CADCraft 0.8's, as its `commands --json` lists them.
    "cadcraft": _says(
        "line|Draws|a line|lines",
        "circle|Draws|a circle|circles",
        "arc|Draws|an arc|arcs",
        "rectang|Draws|a rectangle|rectangles",
        "polygon|Draws|a polygon|polygons",
        "text|Writes|a text|texts|text",
        "mtext|Writes|a text|texts|text",
        "dimlinear|Adds|a dimension|dimensions|text",
        "dimaligned|Adds|a dimension|dimensions|text",
        "dim|Adds|a dimension|dimensions",
        "layer.new|Adds|a layer|layers|name",
        "layer.delete|Deletes|a layer|layers|name",
        "layout.new|Adds|a layout|layouts|name",
        "table.set|Sets|a table cell|table cells|text",
        "erase.selection|Erases|a selection|selections",
    ),
    # PhotoCraft 0.9's, as its `commands --json` lists them.
    "photocraft": _says(
        "type.create|Adds|a type layer|type layers|text",
        "type.insertText|Types into|a type layer|type layers|text",
        "shape.create|Adds|a shape layer|shape layers|kind",
        "layer.duplicate|Duplicates|a layer|layers|name",
        "layer.delete|Deletes|a layer|layers",
        "layer.renameLayer|Renames|a layer|layers|name",
        "layer.setProps|Changes|a layer|layers|name",
        "layer.removeBackground|Removes the background of|a layer|layers",
        "file.placeEmbedded|Places|an image|images",
        "file.placeLinked|Places|a linked image|linked images",
    ),
    # VectorCraft 0.12's, as its `commands --json` lists them.
    "vectorcraft": _says(
        "path.create|Draws|a path|paths",
        "text.create|Adds|a text|texts|text",
        "text.setText|Sets|a text|texts|text",
        "dimension.create|Adds|a dimension|dimensions",
        "layer.new|Adds|a layer|layers|name",
        "layer.delete|Deletes|a selection of layers|selections of layers",
        "artboard.new|Adds|an artboard|artboards|name",
        "artboard.delete|Deletes|an artboard|artboards",
        "paint.setFill|Sets|a fill|fills|color",
        "paint.setStroke|Sets|a stroke|strokes|color",
        "swatch.new|Adds|a swatch|swatches|name",
    ),
    # DesignCraft 0.9's, as its `commands` lists them.
    "designcraft": _says(
        "text.insert|Types|a character|characters|text|text",
        "story.setText|Sets the text of|a story|stories|text",
        "frame.create|Adds|a frame|frames",
        "line.create|Draws|a line|lines",
        "path.create|Draws|a path|paths",
        "file.place|Places|a file|files|name",
        "table.insert|Inserts|a table|tables",
        "note.new|Adds|a note|notes|text",
        "endnote.insert|Inserts|an endnote|endnotes|text",
        "math.insert|Inserts|a math expression|math expressions|latex",
        "object.rename|Renames|an object|objects|name",
    ),
    # FigCraft 0.6's, as its `commands --json` lists them.
    "figcraft": _says(
        "frame.create|Adds|a frame|frames|name",
        "text.create|Adds|a text|texts|text",
        "node.create|Adds|a layer|layers|type",
        "vector.create|Draws|a vector|vectors",
        "image.place|Places|an image|images",
        "edit.delete|Deletes|a selection|selections",
        "edit.duplicate|Duplicates|a selection|selections",
        "object.rename|Renames|a layer|layers|name",
        "page.add|Adds|a page|pages|name",
        "page.delete|Deletes|a page|pages",
        "page.rename|Renames|a page|pages|name",
        "fill.set|Sets|a fill|fills",
        "effect.add|Adds|an effect|effects|type",
    ),
    # FilmCraft 0.8's, as its `commands --json` lists them.
    "filmcraft": _says(
        "file.newSequence|Adds|a sequence|sequences|name",
        "file.newBin|Adds|a bin|bins|name",
        "timeline.place|Places|a clip|clips",
        "sequence.addEdit|Cuts|a clip|clips",
        "sequence.addTracks|Adds|a set of tracks|sets of tracks",
        "sequence.deleteTrack|Deletes|a track|tracks|track",
        "clip.rename|Renames|a clip|clips|name",
        "markers.add|Adds|a marker|markers|name",
        "effects.setParam|Sets|an effect parameter|effect parameters|param",
        "sequence.setTransition|Changes|a transition|transitions",
        "sequence.removeTransition|Removes|a transition|transitions",
    ),
    # EffectCraft 0.11's, as its `commands --json` lists them.
    "effectcraft": _says(
        "comp.new|Adds|a composition|compositions|name",
        "layer.newText|Adds|a text layer|text layers|text",
        "layer.newSolid|Adds|a solid|solids|name",
        "layer.newShape|Adds|a shape layer|shape layers|kind",
        "layer.newNull|Adds|a null|nulls|name",
        "layer.newCamera|Adds|a camera|cameras|name",
        "layer.newLight|Adds|a light|lights|kind",
        "layer.setText|Edits the text of|a layer|layers|text",
        "layer.rename|Renames|a layer|layers|name",
        "layer.addMask|Adds|a mask|masks|shape",
        "prop.addKey|Adds|a keyframe|keyframes|prop",
        "comp.addMarker|Adds|a marker|markers|comment",
    ),
    # SoundCraft 0.8's, as its `commands` lists them.
    "soundcraft": _says(
        "track.new|Adds|a track|tracks|name",
        "track.delete|Deletes|a track|tracks",
        "track.duplicate|Duplicates|a track|tracks",
        "track.rename|Renames|a track|tracks|name",
        "clip.rename|Renames|a clip|clips|name",
        "midi.new_clip|Adds|a MIDI clip|MIDI clips",
        "event.midi_note|Adds|a MIDI note|MIDI notes",
        "mix.insert|Inserts|a plugin|plugins|plugin",
    ),
    # FreeCAD's steps, as the adapter's console script names them (native files ADR-0014).
    "freecad": _says(
        "box|Adds|a box|boxes|name",
        "cylinder|Adds|a cylinder|cylinders|name",
        "sphere|Adds|a sphere|spheres|name",
        "cone|Adds|a cone|cones|name",
        "boolean|Combines|a pair of solids|pairs of solids|name",
        "sketch|Adds|a sketch|sketches|name",
        "sketch.line|Draws|a line|lines",
        "sketch.circle|Draws|a circle|circles",
        "sketch.constraint|Constrains|a sketch|sketches",
        "extrude|Extrudes|a sketch|sketches|name",
        "move|Moves|an object|objects|object",
        "set|Sets|a property|properties|property",
        "remove|Removes|an object|objects|object",
        "sheet|Adds|a spreadsheet|spreadsheets|name",
        "sheet.set|Sets|a spreadsheet cell|spreadsheet cells",
    ),
    # Blender's steps, as the adapter's console script names them (native files ADR-0015).
    "blender": _says(
        "cube|Adds|a cube|cubes|name",
        "sphere|Adds|a sphere|spheres|name",
        "cylinder|Adds|a cylinder|cylinders|name",
        "cone|Adds|a cone|cones|name",
        "plane|Adds|a plane|planes|name",
        "move|Moves|an object|objects|object",
        "material|Adds|a material|materials|name",
        "assign|Assigns|a material|materials|material",
        "modifier|Adds|a modifier|modifiers|type",
        "camera|Adds|a camera|cameras|name",
        "light|Adds|a light|lights|name",
        "collection|Adds|a collection|collections|name",
        "set|Sets|a property|properties|property",
        "remove|Removes|an object|objects|object",
    ),
}
"""Each craft's commands worth saying in its own words, by the craft's name."""

GENERIC: Final = frozenset({"lightcraft"})
"""The crafts said by their commands' names alone, on purpose: LightCraft keeps no native file
(native files ADR-0016), so no proposal is made by its commands."""


def describe(
    app: str | None, commands: Sequence[AppCommand], *, before: int | None = None
) -> ProposalDescription:
    """What a batch of `app`'s commands does: a line, and each command, in words.

    Args:
        app: The app the batch is for, as provenance records it, such as `wordcraft`.
        commands: The batch, as it was applied.
        before: How many pages the file had before the batch, if known.
    """
    table = CRAFTS.get(app or "", {})
    listed = commands[:MOST_ITEMS]
    pages = PAGES.get(app or "", _none)(listed, before)
    items = [
        _item(table.get(command.name), command).model_copy(update={"pages": named})
        for command, named in zip(listed, pages, strict=True)
    ]
    return ProposalDescription(summary=_summary(table, commands), items=items, total=len(commands))


type Pages = Callable[[Sequence[AppCommand], int | None], list[list[int]]]
"""The pages each of a batch's commands changes, from 1, by its craft: none where it can't say."""


def _none(commands: Sequence[AppCommand], _before: int | None) -> list[list[int]]:
    return [[] for _ in commands]


DECK_REORDERS: Final = frozenset(
    {
        "slide.duplicate",
        "slide.delete",
        "slide.move",
        "slide.go",
        "slide.next",
        "slide.previous",
        "slide.first",
        "slide.last",
        "slide.selectSlides",
        "slide.fromOutline",
        "section.remove",
        "edit.cut",
        "edit.paste",
        "edit.delete",
        "window.next",
        "file.recovery.open",
    }
)
"""DeckCraft's commands that add, remove, move or choose a slide other than by `slide.new`: past
one, the batch's slides can't be numbered from its commands alone."""


def _deck(commands: Sequence[AppCommand], before: int | None) -> list[list[int]]:
    """The slides a deck's batch adds, numbered as they end.

    DeckCraft 0.7 adds one after the current slide, or at `at`, no further than the end, and makes
    it current; a file opens at its first. A command in `DECK_REORDERS` leaves every slide
    unnumbered.
    """
    if any(command.name in DECK_REORDERS for command in commands):
        return _none(commands, before)
    added: dict[int, int] = {}  # the command's place in the batch: its slide's index, from 0
    current, count = 0, before
    for at, command in enumerate(commands):
        if command.name != "slide.new":
            continue
        asked = command.args.get("at")
        index = asked if isinstance(asked, int) and asked >= 0 else current + 1
        if count is not None:
            index = min(index, count)
            count += 1
        added = {each: slide + (slide >= index) for each, slide in added.items()}
        added[at] = current = index
    return [[added[at] + 1] if at in added else [] for at in range(len(commands))]


WORD_PAGED: Final = frozenset(
    {
        "insert.editHeader",
        "insert.editFooter",
        "insert.createHeader",
        "insert.createFooter",
    }
)
"""WordCraft's commands that name the page they act on, as `page`, from 0. Its words flow, so no
other command's page is known before the file is laid out."""


def _word(commands: Sequence[AppCommand], _before: int | None) -> list[list[int]]:
    return [
        [page + 1]
        if command.name in WORD_PAGED
        and isinstance(page := command.args.get("page"), int)
        and page >= 0
        else []
        for command in commands
    ]


PAGES: Final[Mapping[str, Pages]] = {"deckcraft": _deck, "wordcraft": _word}
"""How each craft that can names the pages a command changes."""


def _item(says: Says | None, command: AppCommand) -> CommandChange:
    args = {key: "…" if key in MASKED else _cut(value) for key, value in command.args.items()}
    says = None if says is None or _uncounted(says, command) else says
    if says is None:
        quoted = next((v for k in QUOTABLE if isinstance(v := command.args.get(k), str)), None)
        text = command.name if quoted is None else f"{command.name}: {_quote(quoted)}"
    elif says.counts:
        text = f"{says.verb} {_quote(command.args.get(says.counts))}"
    else:
        name = command.args.get(says.named) if says.named else None
        text = f"{says.verb} {says.one}" + (f": {_quote(name)}" if isinstance(name, str) else "")
    return CommandChange(text=text, name=command.name, args=args)


def _uncounted(says: Says, command: AppCommand) -> bool:
    """Whether a command whose characters are counted has none to count: said by its name."""
    value = command.args.get(says.counts)
    return bool(says.counts) and not (isinstance(value, str) and value)


def _summary(table: Mapping[str, Says], commands: Sequence[AppCommand]) -> str:
    if not commands:
        return "Changes nothing."
    counted: dict[tuple[str, str, str], int] = {}
    names: dict[tuple[str, str, str], list[str]] = {}
    others = 0
    for command in commands:
        says = table.get(command.name)
        if says is None or _uncounted(says, command):
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
    return f"“{_short(str(value))}”"


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
