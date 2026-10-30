"""A stand-in for `pdfcraft-cli mcp`: PdfCraft's MCP tools, as far as the adapter calls them.

Its documents are a PDF's header and then JSON: their pages, each its words, and the comments on
them. Every command names the open document by `doc`, and a blank one is made by `doc_create`,
as PdfCraft does. `--mode` makes it misbehave as a test needs:

- `repairing`: says it repaired every document it opens.
- `nameless`: makes a blank document without naming it.

Run as `python -I fake_cli.py --mode MODE mcp --root ROOT`.
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
HEADER = b"%PDF-1.7\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="")
    parser.add_argument("command")
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    serve(args.mode, args.root.resolve())


def serve(mode: str, root: Path) -> None:
    server = MCPServer("pdfcraft", version="0.8.0")
    documents: dict[int, dict[str, Any]] = {}

    def replied(value: Any, *, error: bool = False) -> CallToolResult:
        return CallToolResult(
            content=[TextContent(text=json.dumps(value))], structured_content=value, is_error=error
        )

    def opened(doc: int) -> dict[str, Any]:
        if doc not in documents:
            raise ToolError(f"no open document with id {doc} (see doc_list)")
        return documents[doc]

    def confined(path: str) -> Path:
        if not Path(path).resolve().is_relative_to(root):
            raise ToolError(f"{path} is outside the allowed directory {root}")
        return Path(path)

    def run(command: str, params: dict[str, Any]) -> Any:
        if command == "file.open":
            content = confined(params["path"]).read_bytes()
            if not content.startswith(HEADER):
                raise ToolError("the file is not a readable PDF")
            documents[len(documents) + 1] = json.loads(content[len(HEADER) :])
            return {"doc": len(documents), "pages": len(documents[len(documents)]["pages"])}
        if command == "file.save":
            confined(params["path"]).write_bytes(
                HEADER + json.dumps(opened(params["doc"])).encode()
            )
            return {"bytes": 1}
        if command == "edit.add_text":
            opened(params["doc"])["pages"][params["page"] - 1].append(params["text"])
            return {"added": True}
        if command == "comment.add":
            opened(params["doc"])["comments"].append({"page": 1, "contents": params["text"]})
            return {"index": 1}
        raise ToolError(f'command "{command}" has no headless tool; see command_list')

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
                results.append({"ok": True, "result": run(step["id"], step.get("params", {}))})
            except ToolError as error:
                results.append({"ok": False, "error": str(error)})
                break
        failed = sum(not r["ok"] for r in results)
        return replied({"failed": failed, "results": results}, error=failed > 0)

    @server.tool()
    async def doc_create() -> CallToolResult:
        # PdfCraft takes `from`, which no Python parameter can be named: the live tests hold it.
        documents[len(documents) + 1] = {"pages": [[]], "comments": []}
        return replied({"name": "Untitled.pdf"} if mode == "nameless" else {"doc": len(documents)})

    @server.tool()
    async def doc_inspect(doc: int) -> CallToolResult:
        pages = [{"page": n} for n, _ in enumerate(opened(doc)["pages"], 1)]
        outline = [{"title": "Start", "page": 1, "children": [{"title": "Detail", "children": []}]}]
        repairs = (
            ["rebuilt cross-reference index from 7 object headers"] if mode == "repairing" else []
        )
        return replied({"pages": pages, "outline": outline, "repairs": repairs, "file_size": 9})

    @server.tool()
    async def text_extract(doc: int) -> CallToolResult:
        pages = [
            {"page": n, "text": "\n".join(words)} for n, words in enumerate(opened(doc)["pages"], 1)
        ]
        return replied({"pages": pages})

    @server.tool()
    async def comment_list(doc: int) -> CallToolResult:
        comments = opened(doc)["comments"]
        return replied({"comments": comments, "count": len(comments)})

    @server.tool()
    async def render_preview(doc: int, page: int = 1, max_side: int = 1024) -> Image:
        if not 1 <= page <= len(opened(doc)["pages"]) or max_side < 1:
            raise ToolError(f"no page {page}")
        return Image(data=PNG, format="png")

    @server.tool()
    async def command_list(filter: str = "") -> CallToolResult:
        listed = [{"id": "edit.add_text", "label": "Add text", "menu": "Edit", "params": {}}]
        return replied({"commands": [c for c in listed if filter in c["id"]] * 11})

    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()
