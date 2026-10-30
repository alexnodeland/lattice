"""A stand-in for `deckcraft-cli mcp`: DeckCraft's MCP tools, as far as the adapter calls them.

Its decks are zips, as a `.pptx` is, whose content types say they are presentations: their
slides as JSON in `ppt/deck.json`, each with its title, its words and its comments. It confines
nothing, as DeckCraft doesn't, and numbers slides from 0, as DeckCraft does.

Run as `python -I fake_cli.py mcp`.
"""

import asyncio
import base64
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # `python -I` leaves it off

from tests.files.craft.stdio_mcp import CallToolResult, Image, MCPServer, TextContent, ToolError

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)
TYPES = (
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Override PartName="/ppt/presentation.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/></Types>'
)
COMMANDS = [
    {"id": "slide.new", "label": "New Slide", "menu": ["Home", "Slides"], "params": "{layout?}"},
    {"id": "comment.add", "label": "New Comment", "menu": ["Review"], "params": "{text}"},
    {"id": "app.quit", "label": "Quit", "menu": ["App"], "params": "{}"},
]


def main() -> None:
    server = MCPServer("deckcraft", version="0.7.0")
    deck: dict[str, Any] = {"slides": []}

    def run(command: str, params: dict[str, Any]) -> Any:
        if command == "slide.new":
            deck["slides"].append({"title": params.get("title", ""), "words": [], "comments": []})
            return {"index": len(deck["slides"]) - 1}
        if command == "text.add":
            deck["slides"][-1]["words"].append(params["text"])
            return None
        if command == "comment.add":
            deck["slides"][-1]["comments"].append({"author": "Presenter", "text": params["text"]})
            return {"index": 0}
        if command == "comment.list":
            return deck["slides"][params["slide"]]["comments"]
        raise ToolError(f"unknown command `{command}`")

    @server.tool()
    async def new_presentation() -> str:
        deck.update(slides=[{"title": "", "words": [], "comments": []}])
        return json.dumps({"document": 0})

    @server.tool()
    async def open_presentation(path: str) -> str:
        try:
            with zipfile.ZipFile(path) as archive:
                deck.update(json.loads(archive.read("ppt/deck.json")))
        except (zipfile.BadZipFile, KeyError) as error:
            raise ToolError(f"not a PPTX file: {error}") from None
        return json.dumps({"document": 1, "slides": len(deck["slides"])})

    @server.tool()
    async def batch(commands: list[dict[str, Any]]) -> CallToolResult:
        steps: list[dict[str, Any]] = []
        for step in commands:
            try:
                result = run(step["command"], step.get("params", {}))
            except ToolError as error:
                steps.append({"command": step["command"], "ok": False, "error": str(error)})
                return CallToolResult(content=[TextContent(text=json.dumps(steps))], is_error=True)
            steps.append({"command": step["command"], "ok": True, "result": result})
        return CallToolResult(content=[TextContent(text=json.dumps(steps))])

    @server.tool()
    async def run_command(command: str, params: dict[str, Any] | None = None) -> str:
        return json.dumps(run(command, params or {}))

    @server.tool()
    async def save_presentation(path: str) -> str:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("[Content_Types].xml", TYPES)
            archive.writestr("ppt/deck.json", json.dumps(deck))
        return json.dumps({"path": path})

    @server.tool()
    async def inspect_document() -> str:
        slides = [{"index": i, "title": s["title"]} for i, s in enumerate(deck["slides"])]
        return json.dumps({"slides": slides, "path": "/elsewhere", "dirty": False})

    @server.tool()
    async def inspect_slide(index: int) -> str:
        slide = deck["slides"][index]
        shapes = [{"id": 2, "text": slide["title"]}, *({"text": w} for w in slide["words"])]
        if slide["words"]:
            shapes.append({"kind": "table", "table": {"cells": [["a", "b"], ["c", "d"]]}})
        notes = "Say hello" if slide["title"] else ""
        return json.dumps(
            {"index": index, "title": slide["title"], "notes": notes, "shapes": shapes}
        )

    @server.tool()
    async def render_slide(slide: int = 0, scale: float = 1) -> Image:
        del scale
        if not 0 <= slide < len(deck["slides"]):
            raise ToolError(f"no slide {slide}")
        return Image(data=PNG, format="png")

    @server.tool()
    async def list_commands(filter: str = "") -> str:
        found = [c for c in COMMANDS if filter.lower() in json.dumps(c).lower()]
        return json.dumps(found * 6)

    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()
