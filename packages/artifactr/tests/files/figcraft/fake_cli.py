"""A stand-in for `figcraft-cli mcp`: FigCraft's MCP tools, as far as the adapter calls them.

Its designs are `.figcraft`s as FigCraft writes them, as far as the adapter reads them: a zip
whose `document.json` says its format first, then holds its words and comments. Each session
starts with an untitled design, as FigCraft's does, and it confines nothing, as FigCraft doesn't.
Its replies are JSON in text, and its list a command a line, as FigCraft's are. Run as
`python -I fake_cli.py mcp`.
"""

import asyncio
import base64
import io
import json
import zipfile
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, ImageContent, TextContent

LISTED = """\
3 commands (id — label [menu] (shortcut) params; * = undoable):
text.create* — Text {text, x, y}
view.comments — Comments [View] (Shift+C) {on?}
comment.add* — Add comment {x, y, text}
not a command"""


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def main() -> None:
    server = MCPServer("figcraft", version="0.6.0")
    design: dict[str, Any] = {"words": [], "comments": []}

    @server.tool()
    def open_file(path: str) -> CallToolResult:
        with zipfile.ZipFile(Path(path)) as archive:
            design.update(json.loads(archive.read("document.json")))
        return replied({"opened": {"index": 1, "repairs": []}})

    @server.tool()
    async def batch(commands: list[dict[str, Any]]) -> CallToolResult:
        for step in commands:
            params = step.get("params", {})
            if step["command"] == "text.create":
                design["words"].append(params["text"])
            elif step["command"] == "comment.add":
                design["comments"].append(
                    {"id": len(design["comments"]) + 1, "text": params["text"]}
                )
            elif step["command"] == "page.background":
                design["background"] = params["color"]
            else:
                raise ToolError(f"unknown command `{step['command']}`")
        return replied([{"id": 2}] * len(commands))

    @server.tool()
    def save_file(path: str) -> CallToolResult:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("document.json", json.dumps({"format": "figcraft", **design}))
        Path(path).write_bytes(buffer.getvalue())
        return replied({"bytes": len(buffer.getvalue()), "path": path})

    @server.tool()
    async def inspect_document(
        depth: int = 1,
    ) -> CallToolResult:
        texts = [{"name": w, "type": "TEXT", "characters": w} for w in design["words"]]
        frame = {"name": "Frame", "type": "FRAME", "children": texts}
        pages = [
            {
                "name": "Page 1",
                "type": "PAGE",
                "background": design.get("background", "#F5F5F5CC"),
                "children": [frame] if depth > 1 else [],
            }
        ]
        return replied({"pages": pages})

    @server.tool()
    async def run_command(command: str, params: dict[str, Any] | None = None) -> CallToolResult:
        params = params or {}
        if command == "page.select" and params.get("index") == 0:
            return replied({"ok": True})
        if command == "page.select":
            raise ToolError("invalid parameters for `page.select`: no such page")
        if command != "comment.list" or params.get("page") != "all":
            raise ToolError(f"unknown command `{command}`")
        return replied({"comments": design["comments"]})

    @server.tool()
    async def screenshot() -> CallToolResult:
        if "Unrenderable" in design["words"]:
            raise ToolError("the renderer crashed")
        if not design["words"]:
            # As FigCraft words it: its own text, which ToolError would prefix.
            return CallToolResult(
                content=[TextContent(text="the current page is empty: nothing to render")],
                is_error=True,
            )
        data = base64.b64encode(PNG).decode()
        return CallToolResult(content=[ImageContent(data=data, mime_type="image/png")])

    @server.tool()
    async def list_commands(filter: str = "") -> CallToolResult:
        found = [line for line in LISTED.splitlines()[1:] if filter in line] * 4
        return CallToolResult(
            content=[TextContent(text="\n".join([LISTED.splitlines()[0], *found]))]
        )

    asyncio.run(server.run_stdio_async())


def replied(value: Any) -> CallToolResult:
    """A reply in text only, as FigCraft's are."""
    return CallToolResult(content=[TextContent(text=json.dumps(value))])


if __name__ == "__main__":
    main()
