"""Connected apps: an operator's own FreeCAD or Blender, through its vetted MCP server (ADR-0085).

The operator runs the app, a desktop window or a headless instance they trust, with its community
server's add-on; the runner spawns the server on stdio for each call, on the same machine, and
the agent gets the app's tools: its reads and edits while `connect:<app>` is on, and, opt-in at
every level and approved by a person on every call, its code and network tools. Nothing here
opens a file for anyone: a file the operator saves is uploaded as a native file, and scanned.
"""

from artifactr.connect.connection import LOOPBACK, Connection, ConnectionFailed
from artifactr.connect.registry import (
    BLENDER,
    FREECAD,
    PROTECTED,
    ConnectedServer,
    Risk,
    Vetted,
    digest,
)
from artifactr.connect.scan import scan
from artifactr.connect.tools import (
    CODE_BYTES,
    DESCRIPTION_CHARS,
    IMAGE_BYTES,
    IMAGES,
    REPLY_CHARS,
    RUN_CODE,
    connected_app_tools,
)

__all__ = [
    "BLENDER",
    "CODE_BYTES",
    "DESCRIPTION_CHARS",
    "FREECAD",
    "IMAGES",
    "IMAGE_BYTES",
    "LOOPBACK",
    "PROTECTED",
    "REPLY_CHARS",
    "RUN_CODE",
    "ConnectedServer",
    "Connection",
    "ConnectionFailed",
    "Risk",
    "Vetted",
    "connected_app_tools",
    "digest",
    "scan",
]
