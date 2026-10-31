"""A stand-in for `designcraft-cli mcp`: DesignCraft's MCP tools, as far as the adapter calls them.

Its layouts are zips, as an IDML package is: its `mimetype`, and its stories as JSON. It opens and
exports them by `execute`'s `file.openIdml` and `file.exportIdml`, numbers pages from 0, and
replies in text only, as DesignCraft does; `--mode garbled` answers a failed batch with text that
isn't its usual object.

Run as `python -I fake_cli.py --mode MODE mcp ...`.
"""

import argparse
import asyncio
import base64
import io
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
IDML = "application/vnd.adobe.indesign-idml-package"
COMMANDS = [
    {"id": "frame.create", "label": "Text Frame", "menu": ["Object"], "params": "{rect, text}"},
    {"id": "layout.pages.insert", "label": "Insert Pages", "menu": ["Layout", "Pages"]},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="")
    parser.add_argument("command")
    args, _ = parser.parse_known_args()
    serve(args.mode)


def serve(mode: str) -> None:
    server = MCPServer("designcraft", version="0.9.0")
    layout: dict[str, Any] = {"stories": [], "pages": 1}

    def run(command: str, params: dict[str, Any]) -> dict[str, Any]:
        if command == "file.openIdml":
            with zipfile.ZipFile(params["path"]) as archive:
                layout.update(json.loads(archive.read("designmap.json")))
            return {"index": 1, "warnings": []}
        if command == "file.exportIdml":
            Path(params["path"]).write_bytes(_zipped(layout))
            return {"path": params["path"]}
        if command == "frame.create":
            layout["stories"].append(params["text"])
            return {"id": 8, "story": len(layout["stories"])}
        raise ToolError(f"unknown command `{command}`")

    @server.tool()
    async def new_document() -> CallToolResult:
        layout.update(stories=[], pages=1)
        return replied({"index": 1})

    @server.tool()
    async def execute(command: str, params: dict[str, Any] | None = None) -> CallToolResult:
        return replied(run(command, params or {}))

    @server.tool()
    async def batch(commands: list[dict[str, Any]]) -> CallToolResult:
        results: list[dict[str, Any]] = []
        for index, step in enumerate(commands):
            try:
                results.append(run(step["command"], step.get("params", {})))
            except ToolError as error:
                failed = {
                    "failedCommand": step["command"],
                    "failedIndex": index,
                    "error": str(error),
                }
                text = "it failed" if mode == "garbled" else json.dumps(failed)
                return CallToolResult(content=[TextContent(text=text)], is_error=True)
        return replied({"completed": len(results), "results": results})

    @server.tool()
    async def inspect_document() -> CallToolResult:
        stories = [{"id": n + 1, "preview": s[:20]} for n, s in enumerate(layout["stories"])]
        return replied({"pageCount": layout["pages"], "stories": stories})

    @server.tool()
    async def get_story(story: int) -> CallToolResult:
        return replied({"id": story, "text": layout["stories"][story - 1]})

    @server.tool()
    async def render_page(page: int = 0, scale: float = 1) -> Image:
        del scale
        if not 0 <= page < layout["pages"]:
            raise ToolError(f"no page {page} (indices are 0-based)")
        return Image(data=PNG, format="png")

    @server.tool()
    async def list_commands(filter: str = "") -> CallToolResult:
        found = [c for c in COMMANDS if filter.lower() in json.dumps(c).lower()]
        return replied({"commands": found * 6})

    asyncio.run(server.run_stdio_async())


def replied(value: Any) -> CallToolResult:
    """A reply in text only, as DesignCraft's are."""
    return CallToolResult(content=[TextContent(text=json.dumps(value))])


def _zipped(layout: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", IDML)
        archive.writestr("designmap.json", json.dumps(layout))
    return buffer.getvalue()


if __name__ == "__main__":
    main()
