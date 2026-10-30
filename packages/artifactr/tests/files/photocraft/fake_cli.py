"""A stand-in for `photocraft-cli mcp`: PhotoCraft's MCP tools, as far as the adapter calls them.

Its documents are JSON after a `.psd`'s header: their layers, top to bottom, and their notes. It
opens, makes and saves them through `doc_open`, `doc_new` and `doc_save`, refuses `file.open`, and
runs commands on the document open last, replying in text only, as PhotoCraft does. A batch
with a step `crash` fails whole, with no results. It confines its files to the read
and write roots it is given.

Run as `python -I fake_cli.py mcp --automation-read-root IN --automation-write-root OUT`.
"""

import argparse
import asyncio
import base64
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # `python -I` leaves it off

from tests.files.craft.stdio_mcp import CallToolResult, Image, MCPServer, TextContent, ToolError

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)
HEADER = b"8BPS\x00\x01"
COMMANDS = [
    {"id": "layer.new.layer", "label": "New Layer", "menu": ["Layer", "New"], "params": "{name}"},
    {"id": "type.create", "label": "New Type Layer", "menu": ["Layer"], "params": "{text}"},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--automation-read-root", type=Path, required=True)
    parser.add_argument("--automation-write-root", type=Path, required=True)
    args = parser.parse_args()
    serve(args.automation_read_root.resolve(), args.automation_write_root.resolve())


def serve(read_root: Path, write_root: Path) -> None:
    server = MCPServer("photocraft", version="0.9.0")
    document: dict[str, Any] = {"layers": [], "notes": []}

    def confined(path: str, root: Path) -> Path:
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(root):
            raise ToolError(f"automation path rejected: outside the root {root}: {path}")
        return resolved

    def run(command: str, params: dict[str, Any]) -> dict[str, Any]:
        if command == "layer.new.layer":
            document["layers"].insert(0, {"name": params["name"], "kind": "Pixel"})
        elif command == "type.create":
            text = {"name": params["text"], "kind": "Type", "text": {"text": params["text"]}}
            document["layers"].insert(0, {"name": "Group", "kind": "Group", "children": [text]})
        else:
            raise ToolError(f"unknown command `{command}`")
        return {"layer": len(document["layers"])}

    @server.tool()
    async def doc_new(width: int = 1920, height: int = 1080) -> CallToolResult:
        document.update(layers=[{"name": "Background", "kind": "Pixel"}], notes=[])
        return replied({"document": 0, "size": [width, height]})

    @server.tool()
    def doc_open(path: str) -> CallToolResult:
        content = confined(path, read_root).read_bytes()
        if not content.startswith(HEADER):
            raise ToolError("codec: unrecognized image format")
        document.update(json.loads(content.removeprefix(HEADER)))
        return replied({"index": 0, "layers": len(document["layers"])})

    @server.tool()
    def doc_save(path: str) -> CallToolResult:
        confined(path, write_root).write_bytes(HEADER + json.dumps(document).encode())
        return replied({"path": path, "warnings": []})

    @server.tool()
    async def command_batch(
        steps: list[dict[str, Any]], stop_on_error: bool = True
    ) -> CallToolResult:
        if any(step["id"] == "crash" for step in steps):
            raise ToolError("the batch crashed")
        results: list[dict[str, Any]] = []
        for step in steps:
            try:
                results.append({"ok": True, "result": run(step["id"], step.get("params") or {})})
            except ToolError as error:
                results.append({"ok": False, "error": str(error)})
                if stop_on_error:
                    break
        failed = sum(not r["ok"] for r in results)
        return replied({"completed": len(results) - failed, "failed": failed, "results": results})

    @server.tool()
    async def doc_inspect() -> CallToolResult:
        return replied({"layers": document["layers"], "notes": document["notes"], "width": 8})

    @server.tool()
    async def render_preview(max_side: int = 1024) -> Image:
        if max_side < 1:
            raise ToolError("max_side must be at least 1")
        return Image(data=PNG, format="png")

    @server.tool()
    async def command_list(filter: str = "") -> CallToolResult:
        return replied([c for c in COMMANDS if filter.lower() in json.dumps(c).lower()] * 6)

    asyncio.run(server.run_stdio_async())


def replied(value: Any) -> CallToolResult:
    """A reply in text only, as PhotoCraft's are."""
    return CallToolResult(content=[TextContent(text=json.dumps(value))])


if __name__ == "__main__":
    main()
