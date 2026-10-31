"""The MCP server that the stand-ins for the crafting apps' CLIs serve on stdio, in the stdlib.

The stand-ins (each craft's `fake_cli.py`) declare their tools as they would on the MCP SDK's
`MCPServer`, with the same names, but serve them with this: the SDK took a second or more to
import, once for every call a test made, and on a busy machine that was past a call's deadline.
This starts in milliseconds. It speaks what the adapter's client asks of a server (`initialize`,
`tools/list` and `tools/call`, newline-delimited JSON-RPC), one request at a time, and replies as
`MCPServer` does: text for a `str`, an image for an `Image`, a `CallToolResult` as it is, and a
`ToolError` as an error with its message. Arguments a tool doesn't declare are ignored.

A stand-in runs as `python -I`, which leaves its own directory off `sys.path`, so it puts the
package's root there before it imports this.
"""

import base64
import inspect
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

type Tool = Callable[..., Any]


class ToolError(Exception):
    """A tool's failure, which the caller is told as an error with this message."""


@dataclass
class TextContent:
    text: str
    type: str = "text"

    def wire(self) -> dict[str, Any]:
        return {"type": "text", "text": self.text}


@dataclass
class ImageContent:
    data: str
    mime_type: str
    type: str = "image"

    def wire(self) -> dict[str, Any]:
        return {"type": "image", "data": self.data, "mimeType": self.mime_type}


@dataclass
class Image:
    data: bytes
    format: str

    def wire(self) -> dict[str, Any]:
        data = base64.b64encode(self.data).decode()
        return ImageContent(data=data, mime_type=f"image/{self.format}").wire()


@dataclass
class CallToolResult:
    content: list[TextContent | ImageContent]
    structured_content: Any = None
    is_error: bool = False

    def wire(self) -> dict[str, Any]:
        reply: dict[str, Any] = {
            "content": [part.wire() for part in self.content],
            "isError": self.is_error,
        }
        if self.structured_content is not None:
            reply["structuredContent"] = self.structured_content
        return reply


@dataclass
class MCPServer:
    name: str
    version: str
    tools: dict[str, Tool] = field(default_factory=dict[str, Tool])

    def tool(self) -> Callable[[Tool], Tool]:
        def register(function: Tool) -> Tool:
            self.tools[function.__name__] = function
            return function

        return register

    async def run_stdio_async(self) -> None:
        """Answer requests from stdin on stdout, until stdin closes."""
        for line in sys.stdin:
            message = json.loads(line)
            if "id" not in message:
                continue  # a notification: initialized, cancelled
            result = await self.answer(message["method"], message.get("params") or {})
            reply = {"jsonrpc": "2.0", "id": message["id"], "result": result}
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()

    async def answer(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            return {
                "protocolVersion": params["protocolVersion"],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": self.name, "version": self.version},
            }
        if method == "tools/list":
            return {"tools": [_listed(name, tool) for name, tool in self.tools.items()]}
        if method == "tools/call":
            return (await self.call(params["name"], params.get("arguments") or {})).wire()
        return {}  # ping

    async def call(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        tool = self.tools[name]
        declared = inspect.signature(tool).parameters
        # Arguments the tool doesn't declare are ignored, as MCPServer ignores them.
        taken = {key: value for key, value in arguments.items() if key in declared}
        try:
            replied = tool(**taken)
            if inspect.isawaitable(replied):
                replied = await replied
        except ToolError as error:
            return CallToolResult(content=[TextContent(text=str(error))], is_error=True)
        except Exception as error:
            text = f"Error executing tool {name}: {error}"
            return CallToolResult(content=[TextContent(text=text)], is_error=True)
        if isinstance(replied, CallToolResult):
            return replied
        if isinstance(replied, Image):
            return CallToolResult(content=[ImageContent(**_image(replied))])
        return CallToolResult(content=[TextContent(text=str(replied))])


def _image(image: Image) -> dict[str, str]:
    wire = image.wire()
    return {"data": wire["data"], "mime_type": wire["mimeType"]}


def _listed(name: str, tool: Tool) -> dict[str, Any]:
    properties = {parameter: {} for parameter in inspect.signature(tool).parameters}
    return {"name": name, "inputSchema": {"type": "object", "properties": properties}}
