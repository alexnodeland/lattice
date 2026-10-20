"""A stand-in for `gridcraft-cli mcp`: GridCraft's MCP tools, as far as the adapter calls them.

Its workbooks are zips, as a `.xlsx` is, whose content types say they are workbooks: their
sheets as JSON in `xl/workbook.json`, each sheet's cells by reference. It confines nothing, as
GridCraft doesn't, and runs each command by `execute_command`, having no batch.

Run as `python -I fake_cli.py mcp`.
"""

import asyncio
import json
import zipfile
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

TYPES = (
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Override PartName="/xl/workbook.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>'
)
COMMANDS = [
    {"id": "cell.set", "label": "Enter", "menu": ["Home", "Editing"], "params": "{cell, input}"},
    {"id": "sheet.add", "label": "Insert Sheet", "menu": [], "params": "{name}"},
]


def main() -> None:
    server = MCPServer("gridcraft", version="0.8.0")
    book: dict[str, Any] = {"sheets": {}}

    @server.tool()
    async def new_workbook() -> str:
        book.update(sheets={"Sheet1": {}})
        return json.dumps({"index": 1, "title": "Book1"})

    @server.tool()
    async def open_workbook(path: str) -> str:
        try:
            with zipfile.ZipFile(path) as archive:
                book.update(json.loads(archive.read("xl/workbook.json")))
        except (zipfile.BadZipFile, KeyError) as error:
            raise ToolError(f"open_workbook: {path}: {error}") from None
        return json.dumps({"path": path})

    @server.tool()
    async def execute_command(command: str, params: dict[str, Any] | None = None) -> str:
        params = params or {}
        if command == "cell.set" and params.get("cell", "").isalnum():
            book["sheets"]["Sheet1"][params["cell"]] = params["input"]
        elif command == "sheet.add":
            book["sheets"][params["name"]] = {}
        else:
            raise ToolError(f"execute_command: unknown command `{command}`")
        return json.dumps({"ok": True})

    @server.tool()
    async def save_workbook(path: str) -> str:
        _save(book, path)
        return json.dumps({"path": path})

    @server.tool()
    async def inspect_workbook() -> str:
        sheets = [
            {
                "name": name,
                "usedRange": ":".join(sorted(cells)) or None,
                "tables": [{"name": "Fees"}] if "A1" in cells else [],
            }
            for name, cells in book["sheets"].items()
        ]
        return json.dumps({"sheets": sheets, "path": "/elsewhere", "undo": ["Enter"]})

    @server.tool()
    async def read_range(sheet: str, formatted: bool = False) -> str:
        del formatted
        cells = book["sheets"][sheet]
        return json.dumps({"values": [[cells[ref], None] for ref in sorted(cells)]})

    @server.tool()
    async def list_commands(search: str = "") -> str:
        found = [c for c in COMMANDS if search.lower() in json.dumps(c).lower()]
        return json.dumps(found * 6)

    asyncio.run(server.run_stdio_async())


def _save(book: dict[str, Any], path: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", TYPES)
        archive.writestr("xl/workbook.json", json.dumps(book))


if __name__ == "__main__":
    main()
