"""What a batch of an app's commands does, in words (native files ADR-0020)."""

import ast
from pathlib import Path

import yaml
from pydantic import JsonValue

import artifactr.files
from artifactr.files.app import AppCommand
from artifactr.files.native import describe
from artifactr.files.native.describe import CRAFTS, GENERIC, LONGEST, MOST_ITEMS


def run(name: str, **args: JsonValue) -> AppCommand:
    return AppCommand(name=name, args=args)


def test_a_deck_says_the_slides_it_adds_by_their_titles() -> None:
    titles = ["Title", "Itinerary", "Budget", "Day 1", "Day 2", "Packing"]
    said = describe("deckcraft", [run("slide.new", layout="title", title=t) for t in titles])
    assert said.summary == "Adds 6 slides: Title, Itinerary, Budget, Day 1, Day 2 and 1 more."
    assert said.items[1].text == "Adds a slide: “Itinerary”"
    assert (said.items[1].name, said.items[1].args, said.total) == (
        "slide.new",
        {"layout": "title", "title": "Itinerary"},
        6,
    )


def test_a_document_says_what_it_types_and_inserts() -> None:
    said = describe(
        "wordcraft",
        [
            run("para.heading1"),
            run("text.insert", text="Trip"),
            run("text.newParagraph"),
            run("text.insert", text="Day 1"),
            run("text.newParagraph"),
            run("para.heading2"),
            run("insert.table", rows=3, cols=2),
            run("para.style", style="Quote"),
        ],
    )
    assert said.summary == (
        "Makes 2 headings, types 9 characters, starts 2 new paragraphs, inserts a table"
        " and applies a style."
    )
    assert [item.text for item in said.items[:4]] == [
        "Makes a heading",
        "Types “Trip”",
        "Starts a new paragraph",
        "Types “Day 1”",
    ]
    assert said.items[-1].text == "Applies a style: “Quote”"


def test_one_kind_of_change_is_said_with_no_names_when_none_is_given() -> None:
    assert describe("deckcraft", [run("slide.new")]).summary == "Adds a slide."
    assert describe("deckcraft", [run("slide.new", title=" ")]).summary == "Adds a slide."


def test_commands_no_table_names_are_counted_beside_those_it_does() -> None:
    said = describe("deckcraft", [run("slide.new", title="A"), run("view.zoom", level=2)])
    assert said.summary == "Adds a slide: A and runs another command."
    assert said.items[1].text == "view.zoom"
    two = describe("deckcraft", [run("slide.delete"), run("x"), run("y")])
    assert two.summary == "Deletes a slide and runs 2 other commands."


def test_a_batch_no_table_says_is_said_by_its_commands_names() -> None:
    commands = [run("a.b"), run("a.b"), run("c.d", text="Hi"), *(run(f"e{n}") for n in range(5))]
    said = describe("figcraft", commands)
    assert said.summary == "Runs 8 commands: a.b \N{MULTIPLICATION SIGN}2, c.d, e0, e1, e2, …"
    assert said.items[2].text == "c.d: “Hi”"
    assert describe(None, [run("a.b")]).summary == "Runs a command: a.b."
    assert describe("wordcraft", [run("view.zoom")]).summary == "Runs a command: view.zoom."


def test_an_empty_batch_changes_nothing() -> None:
    assert describe("deckcraft", []).summary == "Changes nothing."


def test_long_batches_and_arguments_are_cut() -> None:
    long = "x" * (LONGEST + 10)
    said = describe(
        "deckcraft", [run("text.set", text=long, cells=[long], cell={"at": long, "n": 1})] * 250
    )
    assert (len(said.items), said.total) == (MOST_ITEMS, 250)
    args = said.items[0].args
    assert args["text"] == f"{'x' * (LONGEST - 1)}…"
    assert args["cells"] == [args["text"]]
    assert args["cell"] == {"at": args["text"], "n": 1}
    assert said.items[0].text == f"Sets a text: “{'x' * 79}…”"
    assert said.summary.startswith("Sets 250 texts: ")
    assert said.summary.endswith("and 245 more.")


def test_a_counted_argument_with_no_text_is_said_by_its_name() -> None:
    said = describe("wordcraft", [run("text.insert", text=3), run("text.insert", text="")])
    assert said.summary == "Runs 2 commands: text.insert \N{MULTIPLICATION SIGN}2."
    assert [item.text for item in said.items] == ["text.insert", "text.insert: “”"]
    mixed = describe("wordcraft", [run("text.insert", text="Hi"), run("text.insert")])
    assert mixed.summary == "Types 2 characters and runs another command."
    assert describe("wordcraft", [run("text.insert", text="a b\n c")] * 2).summary == (
        "Types 12 characters."
    )


def test_only_words_are_quoted_and_a_servers_path_is_never_listed() -> None:
    said = describe("figcraft", [run("x.open", path="/srv/a.png", token="s3cret", label="Logo")])
    assert said.items[0].text == "x.open: “Logo”"
    assert said.items[0].args == {"path": "…", "token": "s3cret", "label": "Logo"}
    assert describe("figcraft", [run("x.open", url="https://x")]).items[0].text == "x.open"
    picture = describe("wordcraft", [run("insert.picture", path="/srv/p.png", alt="Map")])
    assert (picture.items[0].text, picture.items[0].args["path"]) == (
        "Inserts a picture: “Map”",
        "…",
    )


def test_a_deck_numbers_the_slides_it_adds_as_they_end() -> None:
    said = describe(
        "deckcraft",
        [
            run("slide.new", title="A"),
            run("text.set", text="x"),
            run("slide.new", title="B"),
            run("slide.new", title="C", at=0),
            run("slide.new", title="D", at=40),
        ],
        after=7,
    )
    # A after the first slide; B after A; C first, moving A and B on; D clamped to the end.
    assert [item.pages for item in said.items] == [[3], [], [4], [1], [7]]


def test_a_deck_numbers_no_slide_once_a_command_moves_one() -> None:
    said = describe("deckcraft", [run("slide.new"), run("slide.delete", index=0)], after=3)
    assert [item.pages for item in said.items] == [[], []]
    undone = describe("deckcraft", [run("slide.new"), run("edit.undo")], after=1)
    assert [item.pages for item in undone.items] == [[], []]
    # Where the proposal doesn't say how many slides it makes, none is numbered.
    assert describe("deckcraft", [run("slide.new", at=99)]).items[0].pages == []
    assert describe("deckcraft", [run("slide.new", at=99)], after=4).items[0].pages == [4]


def test_a_document_names_only_the_pages_a_command_names() -> None:
    said = describe(
        "wordcraft",
        [run("insert.editHeader", page=2), run("text.insert", text="Hi"), run("insert.footer")],
    )
    assert [item.pages for item in said.items] == [[3], [], []]
    assert describe("gridcraft", [run("cell.set", value=1)]).items[0].pages == []


COPIER = Path(__file__).parents[4] / "stackr" / "copier.yml"
SCRIPTS = Path(artifactr.files.__file__).parent


def test_every_craft_the_template_wires_has_a_table_or_is_said_by_names_on_purpose() -> None:
    crafts = yaml.safe_load(COPIER.read_text())["crafts"]["default"]
    assert set(crafts) - set(CRAFTS) - GENERIC == set()
    assert set(CRAFTS) & GENERIC == set()


def test_a_script_crafts_table_names_only_steps_its_script_runs() -> None:
    for craft in ("freecad", "blender"):
        tree = ast.parse((SCRIPTS / craft / "console" / "script.py").read_text())
        steps = next(
            {key.value for key in node.value.keys if isinstance(key, ast.Constant)}
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "COMMANDS" for t in node.targets)
            and isinstance(node.value, ast.Dict)
        )
        assert set(CRAFTS[craft]) <= steps, craft


def test_each_craft_says_its_commands_in_its_own_verbs() -> None:
    assert describe("gridcraft", [run("cell.set", cell="B2", input="Fees")]).summary == (
        "Enters a cell: Fees."
    )
    assert describe("figcraft", [AppCommand(name="page.add", args={"name": "Home"})]).items[
        0
    ].text == ("Adds a page: “Home”")
    said = describe(
        "blender",
        [
            AppCommand(name="cube", args={"name": "Box"}),
            AppCommand(name="light", args={"name": "Sun", "type": "SUN"}),
        ],
    )
    assert said.summary == "Adds a cube and adds a light."


def test_a_command_with_a_url_or_a_count_is_said_without_either() -> None:
    link = describe("pdfcraft", [run("edit.link", url="https://example.test/secret")])
    assert "example" not in link.items[0].text
    assert describe("gridcraft", [run("home.insertRows", rows="3:5", count=3)]).summary == (
        "Inserts a set of rows."
    )


def test_a_long_batch_of_a_new_table_is_listed_up_to_its_cap_and_cut() -> None:
    said = describe("cadcraft", [run("text", at=[0, 0], text="x" * 500)] * (MOST_ITEMS + 5))
    assert (len(said.items), said.total) == (MOST_ITEMS, MOST_ITEMS + 5)
    assert said.items[0].text == f"Writes a text: “{'x' * 79}…”"
    assert said.summary.startswith(f"Writes {MOST_ITEMS + 5} texts: x")
    assert said.summary.endswith(f"and {MOST_ITEMS} more.")
