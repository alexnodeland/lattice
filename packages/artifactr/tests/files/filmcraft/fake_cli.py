"""A stand-in for `filmcraft-cli mcp`: FilmCraft's MCP tools, as far as the adapter calls them.

Its projects are `.fcproj`s as FilmCraft writes them, as far as the adapter reads them: JSON that
says its format, and its items, with what the stand-in keeps beside them: its bins, its
sequence, its captions, and on open how many media are missing and whether it migrated. It runs
commands on the project open, which none names, and confines nothing, as FilmCraft doesn't. Its
replies are JSON in text, as FilmCraft's are. Run as `python -I fake_cli.py mcp`.
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
TICKS = 254_016_000_000
COMMANDS = [
    {"id": "timeline.razor", "label": "Razor", "menu": [], "params": '{"time":ticks}'},
    {"id": "markers.add", "label": "Add Marker", "menu": ["Markers"], "params": '{"name":str?}'},
]


def main() -> None:
    server = MCPServer("filmcraft", version="0.8.0")
    project: dict[str, Any] = {}

    def blank() -> None:
        project.clear()
        project.update(format="filmcraft.project", project={"items": {}}, bins=[], sequence=None)
        project.update(captions=[])

    def run(command: str, params: dict[str, Any]) -> Any:
        sequence = project["sequence"]
        if command == "file.newProject":
            return blank()
        if command == "file.open":
            project.clear()
            project.update(json.loads(Path(params["path"]).read_text()))
            missing, migrated = project.pop("missing", 0), project.pop("migrated", False)
            return {"migrated": migrated, "missingMedia": missing, "schemaVersion": 15}
        if command == "file.saveCopy":
            Path(params["path"]).write_text(json.dumps(project))
            return {"bytes": 1, "path": params["path"]}
        if command == "file.newSequence":
            project["sequence"] = {"name": params["name"], "duration": 0, "markers": []}
            project["sequence"].update(video=[{"name": "Video 1", "items": []}], audio=[])
            return {"sequence": 7}
        if command == "file.newBin":
            project["bins"].append({"name": params["name"], "children": []})
            return {"bin": len(project["bins"])}
        if command == "file.importMedia" and project["bins"]:
            item = {"name": params["name"], "type": "Movie"}
            project["bins"][-1]["children"].append(item)
            media = {"File": {"path": params["path"]}}
            project["project"]["items"]["8"] = {
                "name": params["name"],
                "kind": {"Media": {"media": media}},
            }
            return {"item": 8}
        if command == "graphics.newText" and sequence:
            sequence["video"][0]["items"].append({"name": params["text"]})
            sequence["duration"] += round(params["seconds"] * TICKS)
            return {"clip": 9}
        if command == "markers.add" and sequence:
            sequence["markers"].append({"name": params["name"], "comment": "", "start": 0})
            return {"marker": 10}
        if command == "captions.add":
            project["captions"].append({"text": params["text"]})
            return {"caption": 11}
        if command == "captions.list":
            return {"tracks": [{"captions": project["captions"]}] if project["captions"] else []}
        raise ToolError(f"unknown command `{command}`")

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
        children = [
            {"name": b["name"], "id": i, "children": b["children"]}
            for i, b in enumerate(project["bins"])
        ]
        if project["sequence"]:
            children.append({"name": project["sequence"]["name"], "type": "Sequence", "item": 7})
        tree = {"project": {"root": {"name": "Untitled", "children": children}}}
        return replied({**tree, "sequence": project["sequence"]})

    @server.tool()
    async def render_preview(seconds: float = 0, max_side: int = 960) -> Image:
        if max_side < 1 or seconds < 0:
            raise ToolError("bad parameters")
        return Image(data=PNG, format="png")

    @server.tool()
    async def command_list(filter: str = "", enabled_only: bool = False) -> CallToolResult:
        return replied([c for c in COMMANDS if filter in json.dumps(c)] * 6)

    blank()
    asyncio.run(server.run_stdio_async())


def replied(value: Any, *, error: bool = False) -> CallToolResult:
    """A reply in text only, as FilmCraft's are."""
    return CallToolResult(content=[TextContent(text=json.dumps(value))], is_error=error)


if __name__ == "__main__":
    main()
