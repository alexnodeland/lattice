"""A stand-in for a `commands`-dialect CLI's `mcp`, as PdfCraft's server speaks it.

Its files are JSON: pages, each with its words, and the number of times they were saved, which
each save stamps. Every command names the open document by `doc`, as `file.open`'s result does.
It confines its files to the roots it is given, `--root` or the read and write roots, and
`--mode` makes it misbehave as a test needs:

- `bare`: lists commands as a bare JSON array, in text, and opens a file naming no document.
- `opaque`: answers `file.open` with text that isn't JSON.
- `listless`: lists commands as something that isn't a list of them.
- `garbled`: answers a failed batch with results that aren't its usual ones.
- `quiet`: answers a failed batch naming no step that failed.
- `lenient`: answers a failed batch as if it had not failed, but for its results.

Run as `python -I fake_commands_cli.py --mode MODE mcp ...`, with `FAKE_ARGS` naming a file it
writes its arguments to.
"""

import argparse
import asyncio
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)
COMMANDS: list[dict[str, Any]] = [
    {
        "id": "page.add",
        "label": "Add a page",
        "menu": "Pages",
        "params": {"properties": {"text": {"type": "string"}}},
    },
    {"id": "page.rotate", "label": "Rotate pages", "menu": ["Pages", "Rotate"], "params": None},
    {"id": "help.about", "label": "About", "params": "{}"},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="")
    parser.add_argument("command")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--automation-read-root", type=Path)
    parser.add_argument("--automation-write-root", type=Path)
    args, _ = parser.parse_known_args()
    Path(os.environ["FAKE_ARGS"]).write_text(json.dumps(sys.argv[1:]))
    read_root = args.root or args.automation_read_root
    write_root = args.root or args.automation_write_root
    serve(args.mode, read_root and read_root.resolve(), write_root and write_root.resolve())


def serve(mode: str, read_root: Path | None, write_root: Path | None) -> None:
    server = MCPServer("toolcraft", version="1.0.0")
    documents: dict[int, dict[str, Any]] = {}

    def confined(path: str, root: Path | None) -> Path:
        resolved = Path(path).resolve()
        if root is not None and not resolved.is_relative_to(root):
            raise ToolError(f"{path} is outside the allowed directory {root}")
        return resolved

    def replied(value: Any, *, error: bool = False) -> CallToolResult:
        text = json.dumps(value)
        return CallToolResult(
            content=[TextContent(text=text)], structured_content=value, is_error=error
        )

    def document(params: dict[str, Any]) -> dict[str, Any]:
        if params.get("doc") not in documents:
            raise ToolError(f"no document {params.get('doc')}")
        return documents[params["doc"]]

    def run(command: str, params: dict[str, Any]) -> dict[str, Any]:
        if command == "file.open":
            opened = json.loads(confined(params["path"], read_root).read_text())
            documents[7] = opened
            return (
                {"name": "source", "pages": len(opened["pages"])} if mode == "bare" else {"doc": 7}
            )
        if command == "file.new":
            documents[8] = {"pages": [], "saves": 0}
            return {"doc": 8}
        if command == "file.save":
            opened = document(params)
            opened["saves"] += 1
            confined(params["path"], write_root).write_text(json.dumps(opened))
            return {"bytes": 1}
        if command == "page.add":
            document(params)["pages"].append(params["text"])
            return {"pages": len(document(params)["pages"])}
        raise ToolError(f'command "{command}" has no headless tool; see command_list')

    @server.tool()
    async def command_run(id: str, params: dict[str, Any] | None = None) -> CallToolResult:
        if mode == "opaque" and id == "file.open":
            return CallToolResult(content=[TextContent(text="opened it")])
        return replied(run(id, params or {}))

    @server.tool()
    async def command_batch(
        steps: list[dict[str, Any]], stop_on_error: bool = True
    ) -> CallToolResult:
        results: list[dict[str, Any]] = []
        for step in steps:
            try:
                results.append({"ok": True, "result": run(step["id"], step.get("params", {}))})
            except ToolError as error:
                results.append({"ok": False, "error": str(error)})
                if stop_on_error:
                    break
        failed = sum(not r["ok"] for r in results)
        if mode == "garbled":
            results = [{"step": "?"}]
        if mode == "quiet":
            results = [{"ok": True}]
        reply = {"completed": len(results) - failed, "failed": failed, "results": results}
        return replied(reply, error=failed > 0 and mode != "lenient")

    @server.tool()
    async def doc_inspect() -> CallToolResult:
        return replied({"documents": [{"doc": key, **d} for key, d in documents.items()]})

    @server.tool()
    async def render_preview(doc: int, page: int = 1, max_side: int = 1024) -> Image:
        opened = documents[doc]
        if not 1 <= page <= len(opened["pages"]) or max_side < 1:
            raise ToolError(f"no page {page}")
        return Image(data=PNG, format="png")

    @server.tool()
    async def command_list(filter: str = "") -> CallToolResult:
        found = [c for c in COMMANDS if filter.lower() in json.dumps(c).lower()]
        if mode == "bare":
            return CallToolResult(content=[TextContent(text=json.dumps(found * 5))])
        if mode == "listless":
            return replied({"commands": "none"})
        return replied({"commands": found * 5})

    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()
