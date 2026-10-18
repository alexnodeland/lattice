"""A stand-in for `wordcraft-cli mcp`: WordCraft's MCP tools, as far as the adapter calls them.

Its documents are zips, as a `.docx` is: their blocks as JSON in `word/document.json`, and in
`docProps/core.xml` the number of times they were saved, which each save stamps, as WordCraft
stamps the time. It confines its files to the read and write roots it is given, as WordCraft
does, and `--mode` makes it misbehave as a test needs:

- `hang`: never answers a call.
- `exit`: exits, unannounced, on the first call.
- `version`: says it is version 0.0.1.
- `textual`: renders a page as text, not a PNG.
- `garbled`: answers a failed batch with text that isn't its usual list.

Run as `python -I fake_cli.py --mode MODE mcp ...`, with `FAKE_PIDS` naming a file it adds its
process id to.
"""

import argparse
import asyncio
import base64
import io
import json
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)
TYPES = (
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Override PartName="/word/document.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
)
COMMANDS = [
    {"id": "text.insert", "label": "Insert Text", "location": "Home", "params": '{"text": s}'},
    {"id": "para.heading1", "label": "Heading 1", "location": "Home > Styles", "params": "{}"},
    {"id": "review.newComment", "label": "New Comment", "location": "Review", "params": "{}"},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="")
    parser.add_argument("command")
    parser.add_argument("--author", default="")
    parser.add_argument("--automation-read-root", type=Path)
    parser.add_argument("--automation-write-root", type=Path)
    args = parser.parse_args()
    with Path(os.environ["FAKE_PIDS"]).open("a") as pids:
        pids.write(f"{os.getpid()}\n")
    sys.stderr.write(f"fake wordcraft-cli: files confined to {args.automation_read_root}\n")
    sys.stderr.flush()
    serve(args.mode, args.automation_read_root.resolve(), args.automation_write_root.resolve())


def serve(mode: str, read_root: Path, write_root: Path) -> None:
    server = MCPServer("wordcraft", version="0.0.1" if mode == "version" else "0.7.0")
    document: dict[str, Any] = {"blocks": [], "comments": [], "saves": 0}

    async def misbehave() -> None:
        if mode == "hang":
            await asyncio.sleep(3600)
        if mode == "exit":
            os._exit(3)

    def confined(path: str, root: Path) -> Path:
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(root):
            raise ToolError(f"automation path rejected: outside the root {root}: {path}")
        return resolved

    @server.tool()
    async def new_document(template: str = "blank") -> str:
        await misbehave()
        document.update(blocks=[], comments=[], saves=0)
        return json.dumps({"template": template})

    @server.tool()
    async def open_document(path: str) -> str:
        await misbehave()
        try:
            with zipfile.ZipFile(confined(path, read_root)) as archive:
                document.update(json.loads(archive.read("word/document.json")))
                document["saves"] = int(archive.read("docProps/core.xml"))
        except (zipfile.BadZipFile, KeyError) as error:
            raise ToolError(f"not a valid zip package: {error}") from None
        return json.dumps({"path": path})

    @server.tool()
    async def batch(commands: list[dict[str, Any]]) -> CallToolResult:
        steps: list[dict[str, Any]] = []
        for step in commands:
            command, params = step["command"], step.get("params", {})
            if command == "text.insert":
                document["blocks"].append({"text": params["text"], "style": "Normal"})
            elif command == "para.heading1" and document["blocks"]:
                document["blocks"][-1]["style"] = "Heading 1"
            elif command == "review.newComment":
                document["comments"].append({"id": len(document["comments"]), **params})
            else:
                steps.append({"command": command, "error": "unknown command", "ok": False})
                text = "it failed" if mode == "garbled" else json.dumps(steps)
                return CallToolResult(content=[TextContent(text=text)], is_error=True)
            steps.append({"command": command, "ok": True})
        return CallToolResult(content=[TextContent(text=json.dumps(steps))])

    @server.tool()
    async def save_document(path: str) -> str:
        document["saves"] += 1
        confined(path, write_root).write_bytes(_zipped(document))
        return json.dumps({"path": path, "saved": True})

    @server.tool()
    async def get_text() -> str:
        return json.dumps({"text": "\n".join(b["text"] for b in document["blocks"])})

    @server.tool()
    async def inspect_document() -> str:
        blocks = [{"index": i, **b} for i, b in enumerate(document["blocks"])]
        return json.dumps({"blocks": blocks, "pages": max(1, len(blocks)), "words": 0})

    @server.tool()
    async def execute(command: str) -> str:
        if command == "review.comments":
            return json.dumps(document["comments"])
        if command == "review.changes":
            return json.dumps([])
        raise ToolError(f"unknown command `{command}`")

    @server.tool()
    async def render_page(page: int = 1, scale: float = 1) -> Image | str:
        del scale
        if not 1 <= page <= max(1, len(document["blocks"])):
            raise ToolError(f"no page {page}")
        return "a page" if mode == "textual" else Image(data=PNG, format="png")

    @server.tool()
    async def list_commands(query: str = "") -> str:
        await misbehave()
        found = [c for c in COMMANDS if query.lower() in json.dumps(c).lower()]
        return json.dumps(found * 5)

    asyncio.run(server.run_stdio_async())


def _zipped(document: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        kept = {"blocks": document["blocks"], "comments": document["comments"]}
        archive.writestr("[Content_Types].xml", TYPES)
        archive.writestr("word/document.json", json.dumps(kept))
        archive.writestr("docProps/core.xml", str(document["saves"]))
    return buffer.getvalue()


if __name__ == "__main__":
    main()
