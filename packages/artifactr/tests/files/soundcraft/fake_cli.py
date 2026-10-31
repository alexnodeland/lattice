"""A stand-in for `soundcraft-cli mcp`: SoundCraft's MCP tools, as far as the adapter calls them.

Its sessions are `.scraft`s as SoundCraft writes them, as far as the adapter reads them: JSON
that says its version, its tracks and busses, its sources, and its markers, with what the
stand-in keeps beside them: on open, the media it misses. It runs commands on the session
open, takes a batch's commands as `calls`, and confines its files to the read and write roots it
is given, as SoundCraft does. Its replies are JSON in text. Run as `python -I fake_cli.py mcp
--automation-read-root IN --automation-write-root OUT`.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # `python -I` leaves it off

from tests.files.craft.stdio_mcp import CallToolResult, MCPServer, TextContent, ToolError

COMMANDS = [
    {"id": "track.new", "label": "New...", "menu": ["Track"], "params": "{kind?, name?}"},
    {"id": "markers.add", "label": "New Memory Location", "menu": [], "params": "{name?, at?}"},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--automation-read-root", type=Path, required=True)
    parser.add_argument("--automation-write-root", type=Path, required=True)
    args = parser.parse_args()
    serve(args.automation_read_root.resolve(), args.automation_write_root.resolve())


def serve(read_root: Path, write_root: Path) -> None:
    server = MCPServer("soundcraft", version="0.8.0")
    session: dict[str, Any] = {}

    def confined(path: str, root: Path) -> Path:
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(root):
            raise ToolError(f"automation path rejected: outside the root {root}: {path}")
        return resolved

    def run(command: str, params: dict[str, Any]) -> Any:
        if command == "track.new":
            track = {"name": params["name"], "kind": params.get("kind", "audio"), "clips": []}
            session["tracks"].append({**track, "comments": params.get("comments", "")})
            return {"tracks": [len(session["tracks"])]}
        if command == "midi.new_clip":
            session["tracks"][params["track"] - 1]["clips"].append({"name": "Clip"})
            return {"clip": 2}
        if command == "mix.new_bus":
            session["busses"].append({"name": params["name"]})
            return {"bus": 3}
        if command == "markers.add":
            session["markers"].append({"name": params["name"], "start": params["at"]})
            return {"id": 4}
        if command == "file.import_audio":
            session["sources"].append({"name": Path(params["path"]).stem})
            return {"source": 5}
        raise ToolError(f"unknown command `{command}`")

    @server.tool()
    async def new_session(name: str = "Untitled") -> CallToolResult:
        session.clear()
        session.update(format_version=1, name=name, tracks=[], busses=[], markers=[], sources=[])
        return replied({"name": name, "sample_rate": 48_000})

    @server.tool()
    def open_session(path: str) -> CallToolResult:
        session.clear()
        session.update(json.loads(confined(path, read_root).read_text()))
        return replied({"missing": session.pop("missing", []), "tracks": len(session["tracks"])})

    @server.tool()
    def save_session(path: str) -> CallToolResult:
        confined(path, write_root).write_text(json.dumps(session))
        return replied({"audio_files_written": 0, "path": path})

    @server.tool()
    async def batch(calls: list[dict[str, Any]], keep_going: bool = False) -> CallToolResult:
        results: list[dict[str, Any]] = []
        for call in calls:
            try:
                result = run(call["command"], call.get("params") or {})
                results.append({"command": call["command"], "ok": True, "result": result})
            except ToolError as error:
                results.append({"command": call["command"], "ok": False, "error": str(error)})
                return replied(results, error=True)
        return replied(results)

    @server.tool()
    async def inspect_session(detail: bool = False) -> CallToolResult:
        return replied(session)

    @server.tool()
    async def list_commands(filter: str = "") -> CallToolResult:
        return replied([c for c in COMMANDS if filter in json.dumps(c)] * 6)

    asyncio.run(server.run_stdio_async())


def replied(value: Any, *, error: bool = False) -> CallToolResult:
    """A reply in text only, as SoundCraft's are."""
    return CallToolResult(content=[TextContent(text=json.dumps(value))], is_error=error)


if __name__ == "__main__":
    main()
