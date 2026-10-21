"""The vetted servers: each app's community MCP server, and every tool it may offer, with its risk.

A tool the entry doesn't name is never offered, so a server that adds a tool in a new version
adds nothing until its entry does (ADR-0085). Each tool's risk was read from the server's source,
at the version the guide names:

- `read` and `edit` act in the operator's open app, through the server's own fixed scripts;
- `code` runs Python the agent writes, and `network` fetches from the internet, from the app;
- `host` acts on the machine the server runs on, the runner's, or reads or writes its files: it
  is never offered.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal

__all__ = ["BLENDER", "FREECAD", "PROTECTED", "ConnectedServer", "Risk"]

Risk = Literal["read", "edit", "code", "network", "host"]
"""What a tool does, and so when it is offered."""

PROTECTED: Final[frozenset[Risk]] = frozenset({"code", "network"})
"""The risks offered only when the operator allows the tool, the workspace's code key is on and
the person holds the action, and run only once a person approves the call."""


@dataclass(frozen=True)
class ConnectedServer:
    """A vetted server: its app, and every tool it may offer, with its risk.

    Raises:
        ValueError: If the app isn't a lowercase name, or a tool's code argument names a tool
            that isn't `code`.
    """

    app: str
    """The app's name: its keys' (`connect:<app>`) and its tools' prefix (`<app>_`)."""

    title: str
    """The app's name, for people: "FreeCAD"."""

    source: str
    """Where the server comes from, for the admin: its repository."""

    tools: Mapping[str, Risk]
    """Every tool it may offer, by the server's own name."""

    code: Mapping[str, str] = field(default_factory=dict[str, str])
    """The argument that holds the code, by each `code` tool."""

    env: Mapping[str, str] = field(default_factory=dict[str, str])
    """What the server is always given in its environment."""

    def __post_init__(self) -> None:
        if not self.app.isalpha() or not self.app.islower():
            raise ValueError(f"an app is a lowercase name, not {self.app!r}")
        if wrong := sorted(name for name in self.code if self.tools.get(name) != "code"):
            raise ValueError(f"only a code tool names its code: {', '.join(wrong)}")

    @property
    def key(self) -> str:
        """The integration that switches its `read` and `edit` tools: `connect:<app>`."""
        return f"connect:{self.app}"

    @property
    def code_key(self) -> str:
        """The integration that switches its `code` and `network` tools: `connect-code:<app>`."""
        return f"connect-code:{self.app}"


FREECAD: Final = ConnectedServer(
    app="freecad",
    title="FreeCAD",
    source="https://github.com/neka-nat/freecad-mcp",
    tools=MappingProxyType(
        {
            "list_documents": "read",
            "get_objects": "read",
            "get_object": "read",
            "get_parts_list": "read",
            "get_view": "read",
            "get_rpc_status": "read",
            "get_async_status": "read",
            "create_document": "edit",
            "create_object": "edit",
            "edit_object": "edit",
            "delete_object": "edit",
            "execute_code": "code",
            "execute_code_async": "code",
            # A fresh FreeCAD on the runner's machine, not the operator's.
            "execute_code_headless": "host",
            # Reopen a document from, or copy a part in from, the runner's disk.
            "reload_document": "host",
            "insert_part_from_library": "host",
            # Starts a solver on the runner's machine.
            "run_fem_analysis": "host",
        }
    ),
    code=MappingProxyType({"execute_code": "code", "execute_code_async": "code"}),
)
"""neka-nat's FreeCAD server: an add-on's XML-RPC server in FreeCAD's window, on port 9875."""

BLENDER: Final = ConnectedServer(
    app="blender",
    title="Blender",
    source="https://github.com/ahujasid/blender-mcp",
    tools=MappingProxyType(
        {
            "get_scene_info": "read",
            "get_addon_status": "read",
            "look": "read",
            "execute_blender_code": "code",
            "search_assets": "network",
            "import_asset": "network",
            "generate_3d": "network",
            # What the server's maker collects: not the agent's to change.
            "disable_telemetry": "host",
            "record_trajectory_feedback": "host",
        }
    ),
    code=MappingProxyType({"execute_blender_code": "code"}),
    env=MappingProxyType({"DISABLE_TELEMETRY": "true"}),
)
"""ahujasid's Blender server: an add-on's socket in Blender, on port 9876, sending no telemetry."""
