"""A stand-in for `effectcraft-cli mcp`: EffectCraft's MCP tools, as far as the adapter calls them.

Its projects are `.ecproj`s as EffectCraft writes them, as far as the adapter reads them: JSON
that says which release saved it, and its items, with what the stand-in keeps beside them: its
active composition, and on open what it repaired. It runs commands on the project open, which
none names, and confines its files to the read and write roots it is given, as EffectCraft
does. Its replies are JSON in text. Run as `python -I fake_cli.py mcp --automation-read-root IN
--automation-write-root OUT`.
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
COMMANDS = [
    {"id": "layer.newText", "label": "Text", "menu": ["Layer", "New"], "params": "{text?}"},
    {"id": "comp.addMarker", "label": "Add Marker", "params": "{time?, comment?}"},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--automation-read-root", type=Path, required=True)
    parser.add_argument("--automation-write-root", type=Path, required=True)
    args = parser.parse_args()
    serve(args.automation_read_root.resolve(), args.automation_write_root.resolve())


def serve(read_root: Path, write_root: Path) -> None:
    server = MCPServer("effectcraft", version="0.11.1")
    project: dict[str, Any] = {}

    def confined(path: str, root: Path) -> Path:
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(root):
            raise ToolError(f"cannot read `{path}`: it is outside the automation roots")
        return resolved

    def blank() -> None:
        project.clear()
        project.update(savedBy="0.11.1", schema=2, items={}, comp=None)

    def item(name: str, kind: str, parent: int | None = None) -> int:
        number = len(project["items"]) + 1
        project["items"][str(number)] = {"name": name, "kind": {"type": kind}, "parent": parent}
        return number

    def run(command: str, params: dict[str, Any]) -> Any:
        comp = project["comp"]
        if command == "file.newProject":
            return blank()
        if command == "file.open":
            project.clear()
            project.update(json.loads(confined(params["path"], read_root).read_text()))
            return {"path": params["path"], "repaired": project.pop("repaired", [])}
        if command == "file.saveAs":
            confined(params["path"], write_root).write_text(json.dumps(project))
            return {"bytes": 1, "path": params["path"]}
        if command == "project.newFolder":
            return {"item": item(params["name"], "Folder", params.get("parent"))}
        if command == "comp.new":
            number = item(params["name"], "Comp", params.get("parent"))
            project["comp"] = {"id": number, "name": params["name"], "markers": []}
            project["comp"].update(duration=params.get("duration", 0), layers=[])
            return {"comp": number}
        if command == "file.import":
            return {"items": [item(Path(params["path"]).name, "Footage")]}
        if command == "layer.newText" and comp:
            layer = {"id": 100 + len(comp["layers"]), "name": params["text"], "type": "Text"}
            comp["layers"].insert(0, layer)
            return {"layer": layer["id"]}
        if command == "layer.newNull" and comp:
            comp["layers"].insert(
                0, {"id": 100 + len(comp["layers"]), "name": "Null", "type": "Null"}
            )
            return {"layer": 1}
        if command == "comp.addMarker" and comp:
            comp["markers"].append({"time": params["time"], "comment": params["comment"]})
            return {"time": params["time"]}
        if command == "prop.get" and comp and params["path"] == "text/sourceText":
            (layer,) = (layer for layer in comp["layers"] if layer["id"] == params["layer"])
            return {"layer": layer["id"], "value": layer["name"], "type": "text"}
        if command == "markers.list" and comp:
            return comp["markers"]
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
        items = [
            {"id": int(k), "type": v["kind"]["type"], **v} for k, v in project["items"].items()
        ]
        listed = [{key: i[key] for key in ("id", "name", "type", "parent")} for i in items]
        return replied({"project": {"items": listed}, "activeComp": project["comp"]})

    @server.tool()
    async def render_preview(time: float = 0, max_side: int = 960) -> Image:
        if max_side < 1 or time < 0:
            raise ToolError("bad parameters")
        return Image(data=PNG, format="png")

    @server.tool()
    async def command_list(filter: str = "", enabled_only: bool = False) -> CallToolResult:
        return replied([c for c in COMMANDS if filter in json.dumps(c)] * 6)

    blank()
    asyncio.run(server.run_stdio_async())


def replied(value: Any, *, error: bool = False) -> CallToolResult:
    """A reply in text only."""
    return CallToolResult(content=[TextContent(text=json.dumps(value))], is_error=error)


if __name__ == "__main__":
    main()
