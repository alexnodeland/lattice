"""A stand-in for `cadcraft-cli mcp`: CADCraft's MCP tools, as far as the adapter calls them.

Its drawings are JSON after the first bytes of the format they are saved in, an ASCII DXF's first
group or a DWG's version, which it saves by the extension it is given, as CADCraft does. It
confines nothing, as CADCraft doesn't.

Its replies are JSON in text, with no structured content, as CADCraft's are. Run as
`python -I fake_cli.py mcp`.
"""

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)
HEADS = {".dxf": b"  0\nSECTION\n", ".dwg": b"AC1032"}
COMMANDS = [
    {"id": "line", "label": "Line", "menu": ["Draw", "Line"], "params": "{points}"},
    {"id": "text", "label": "Single Line Text", "menu": ["Draw", "Text"], "params": "{at, text}"},
]


def main() -> None:
    server = MCPServer("cadcraft", version="0.8.0")
    drawing: dict[str, Any] = {"lines": 0, "texts": []}

    @server.tool()
    async def new_drawing() -> CallToolResult:
        drawing.update(lines=0, texts=[])
        return replied({"index": 1})

    @server.tool()
    def open(path: str) -> CallToolResult:
        content = Path(path).read_bytes()
        head = HEADS[Path(path).suffix]
        if not content.startswith(head):
            raise ToolError(f"not a {Path(path).suffix} file")
        drawing.update(json.loads(content.removeprefix(head)))
        return replied({"entities": drawing["lines"], "index": 1, "warnings": []})

    @server.tool()
    async def execute(command: str, params: dict[str, Any] | None = None) -> CallToolResult:
        if command == "line":
            drawing["lines"] += 1
        elif command == "text":
            drawing["texts"].append((params or {})["text"])
        else:
            raise ToolError(f"unknown command `{command}`")
        return replied({"handles": ["1A"]})

    @server.tool()
    def save(path: str) -> CallToolResult:
        Path(path).write_bytes(HEADS[Path(path).suffix] + json.dumps(drawing).encode())
        return replied({"binary": False, "path": path})

    @server.tool()
    async def inspect_drawing() -> CallToolResult:
        counts = {"Line": drawing["lines"], "Text": len(drawing["texts"])}
        return replied(
            {
                "counts": {kind: count for kind, count in counts.items() if count},
                "layers": [{"name": "0", "on": True}, {"name": "Walls", "on": True}],
                "layouts": ["Layout1"],
            }
        )

    @server.tool()
    async def find_text(limit: int = 200) -> CallToolResult:
        texts = [{"text": text, "layer": "0"} for text in drawing["texts"][:limit]]
        return replied({"count": len(texts), "texts": texts})

    @server.tool()
    async def render(width: int = 2400) -> Image:
        if width < 16:
            raise ToolError("width must be at least 16")
        return Image(data=PNG, format="png")

    @server.tool()
    async def list_commands(filter: str = "") -> CallToolResult:
        return replied([c for c in COMMANDS if filter.lower() in json.dumps(c).lower()] * 6)

    asyncio.run(server.run_stdio_async())


def replied(value: Any) -> CallToolResult:
    """A reply in text only, as CADCraft's are."""
    return CallToolResult(content=[TextContent(text=json.dumps(value))])


if __name__ == "__main__":
    main()
