"""A stand-in for `vectorcraft-cli mcp`: VectorCraft's MCP tools, as far as the adapter calls them.

Its documents are SVGs whose root holds their objects as JSON in a comment, which it saves to
the path it is given. Its commands act on the document open last, naming none, as VectorCraft's
do, and it confines its files to the read and write roots it is given.

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
SVG = '<svg xmlns="http://www.w3.org/2000/svg"><!--{}--></svg>'
COMMANDS = [
    {"id": "type.add", "label": "Type", "menu": ["Type"], "params": "{text}"},
    {"id": "layer.new", "label": "New Layer", "menu": ["Layer"], "params": "{name}"},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--automation-read-root", type=Path)
    parser.add_argument("--automation-write-root", type=Path)
    args = parser.parse_args()
    serve(args.automation_read_root.resolve(), args.automation_write_root.resolve())


def serve(read_root: Path, write_root: Path) -> None:
    server = MCPServer("vectorcraft", version="0.12.0")
    document: dict[str, Any] = {"layers": [], "artboards": 1}

    def confined(path: str, root: Path) -> Path:
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(root):
            raise ToolError(f"automation path rejected: outside the root {root}: {path}")
        return resolved

    def run(command: str, params: dict[str, Any]) -> dict[str, Any]:
        if command == "file.new":
            document.update(layers=[{"name": "Layer 1", "kind": "Layer"}], artboards=1)
        elif command == "document.open":
            _, opened, rest = confined(params["path"], read_root).read_text().partition("<!--")
            held, closed, _ = rest.partition("-->")
            if not (opened and closed):
                raise ToolError("SVG parse error")
            document.update(json.loads(held))
        elif command == "document.save":
            confined(params["path"], write_root).write_text(SVG.format(json.dumps(document)))
        elif command == "layer.new":
            document["layers"].insert(0, {"name": params["name"], "kind": "Layer"})
        elif command == "type.add":
            text = {"name": params["text"], "kind": "Type", "text": params["text"]}
            document["layers"][0].setdefault("children", []).insert(0, text)
        else:
            raise ToolError(f"unknown command `{command}`")
        return {"index": 1}

    @server.tool()
    async def command_run(id: str, params: dict[str, Any] | None = None) -> CallToolResult:
        return replied(run(id, params or {}))

    @server.tool()
    async def command_batch(
        steps: list[dict[str, Any]], stop_on_error: bool = True
    ) -> CallToolResult:
        results: list[dict[str, Any]] = []
        for step in steps:
            try:
                results.append({"ok": True, "result": run(step["id"], step.get("params") or {})})
            except ToolError as error:
                results.append({"ok": False, "error": str(error)})
                break
        failed = sum(not r["ok"] for r in results)
        reply = {"completed": len(results) - failed, "failed": failed, "results": results}
        return replied(reply, error=failed > 0)

    @server.tool()
    async def doc_inspect() -> CallToolResult:
        artboards = [{"name": f"Artboard {i + 1}"} for i in range(document["artboards"])]
        return replied({"artboards": artboards, "layers": document["layers"]})

    @server.tool()
    async def render_preview(artboard: int = 0, max_side: int = 1024) -> Image:
        if not 0 <= artboard < document["artboards"] or max_side < 1:
            raise ToolError(f"render_preview: no artboard {artboard}")
        return Image(data=PNG, format="png")

    @server.tool()
    async def command_list(filter: str = "") -> CallToolResult:
        return replied([c for c in COMMANDS if filter.lower() in json.dumps(c).lower()] * 6)

    asyncio.run(server.run_stdio_async())


def replied(value: Any, *, error: bool = False) -> CallToolResult:
    """A reply in text only, as VectorCraft's are."""
    return CallToolResult(content=[TextContent(text=json.dumps(value))], is_error=error)


if __name__ == "__main__":
    main()
