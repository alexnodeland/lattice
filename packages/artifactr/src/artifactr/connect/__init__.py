"""Connected apps: an operator's own FreeCAD or Blender, through its vetted MCP server (ADR-0085).

The operator runs the app, a desktop window or a headless instance they trust, with its community
server's add-on; the runner spawns the server on stdio for each call, on the same machine, and
the agent gets the app's tools: its reads and edits while `connect:<app>` is on, and, opt-in at
every level and approved by a person on every call, its code and network tools. Nothing here
opens a file for anyone: a file the operator saves is uploaded as a native file, and scanned.
"""

from artifactr.connect.connection import (
    LOOPBACK,
    PER_HOUR,
    RETRY_AFTER,
    TAILNET,
    AppLock,
    Connection,
    ConnectionFailed,
    PerHour,
    ProcessLock,
    ToolsFor,
    per_hour_setting,
    tools_setting,
)
from artifactr.connect.registry import (
    BLENDER,
    FREECAD,
    PROTECTED,
    UNSET,
    ConnectedServer,
    Risk,
    Vetted,
    digest,
)
from artifactr.connect.scan import scan
from artifactr.connect.tools import (
    CALLED,
    CODE_BYTES,
    DESCRIPTION_CHARS,
    IMAGE_BYTES,
    IMAGES,
    PARTS,
    REPLY_CHARS,
    RUN_CODE,
    connected_app_tools,
)

__all__ = [
    "BLENDER",
    "CALLED",
    "CODE_BYTES",
    "DESCRIPTION_CHARS",
    "FREECAD",
    "IMAGES",
    "IMAGE_BYTES",
    "LOOPBACK",
    "PARTS",
    "PER_HOUR",
    "PROTECTED",
    "REPLY_CHARS",
    "RETRY_AFTER",
    "RUN_CODE",
    "TAILNET",
    "UNSET",
    "AppLock",
    "ConnectedServer",
    "Connection",
    "ConnectionFailed",
    "PerHour",
    "ProcessLock",
    "Risk",
    "ToolsFor",
    "Vetted",
    "connected_app_tools",
    "digest",
    "per_hour_setting",
    "scan",
    "tools_setting",
]
