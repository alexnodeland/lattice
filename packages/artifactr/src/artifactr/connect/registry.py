"""The vetted servers: each app's community MCP server, and every tool it may offer, pinned.

Each tool is vetted at one version of its server: its risk, read from the server's source, and a
digest of what the server says it is, its name, description and input schema. A tool the entry
doesn't name is never offered, and neither is one whose digest no longer matches, so a server that
adds a tool, or changes one, changes nothing until its entry is vetted again (ADR-0085):

- `read` and `edit` act in the operator's open app, through the server's own fixed scripts;
- `code` runs Python the agent writes, and `network` fetches from the internet, from the app;
- `host` acts on the machine the server runs on, the runner's, or reads or writes its files, or
  changes what the server's maker collects: it is never offered.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final, Literal, NamedTuple

from lattice_core.capabilities import Tier

__all__ = [
    "BLENDER",
    "FREECAD",
    "PROTECTED",
    "TIERS",
    "UNSET",
    "ConnectedServer",
    "Risk",
    "Vetted",
    "digest",
]

Risk = Literal["read", "edit", "code", "network", "host"]
"""What a tool does, and so when it is offered."""

PROTECTED: Final[frozenset[Risk]] = frozenset({"code", "network"})
"""The risks offered only when the operator allows the tool, the workspace's code key is on and
the person holds the action, and run only once a person who holds it approves the call."""

TIERS: Final[Mapping[Risk, Tier | None]] = MappingProxyType(
    {"read": "read", "edit": "write", "code": "run_code", "network": "outbound", "host": None}
)
"""Each risk's capability tier (lattice RFC-0011): a `read` tool reads, an `edit` tool writes, a
`code` tool runs code, and a `network` tool reaches outside the deployment. A `host` tool has no
tier, since it is never offered (artifactr ADR-0099)."""


class Vetted(NamedTuple):
    """One tool, as it was vetted: its risk, and the digest of what the server said it is."""

    risk: Risk
    digest: str


def digest(name: str, description: str | None, input_schema: Mapping[str, Any]) -> str:
    """The SHA-256 of a tool's name, description and input schema, as canonical JSON.

    Escaped to ASCII, so text no encoding takes, a lone surrogate, digests too, and can't match.
    """
    told = {"name": name, "description": description or "", "input_schema": input_schema}
    canonical = json.dumps(told, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


UNSET: Final = frozenset({"ExpressionEngine", "Proxy"})
"""Properties no edit sets by name: an expression is code FreeCAD evaluates, and a proxy is an
object's Python."""

Reach = tuple[str, Mapping[str, str], tuple[str, str] | None]
"""Where a network tool fetches from: the argument that picks its service, what each service
reaches, and an argument naming an address or a path of the model's choosing, with what it
means."""


@dataclass(frozen=True)
class ConnectedServer:
    """A vetted server: its app, the version vetted, and every tool it may offer.

    Raises:
        ValueError: If the app isn't a lowercase ASCII name, or a code tool names no code
            argument, or another tool names one.
    """

    app: str
    """The app's name: its keys' (`connect:<app>`) and its tools' prefix (`<app>_`)."""

    title: str
    """The app's name, for people: "FreeCAD"."""

    source: str
    """Where the server comes from, for the admin: its repository."""

    version: str
    """The release vetted, as an installer names it: `freecad-mcp==0.1.27`."""

    reported_version: str
    """The version that release says it is as it starts, which a server must say: its own, and
    not always its release's (FreeCAD's says none), so it catches an accident, not a forgery."""

    tools: Mapping[str, Vetted]
    """Every tool it may offer, by the server's own name."""

    code: Mapping[str, str] = field(default_factory=dict[str, str])
    """The argument that holds the code, by each `code` tool."""

    reaches: Mapping[str, Reach] = field(default_factory=dict[str, Reach])
    """Where each `network` tool fetches from, which its approver is shown: the argument that
    names the service, the hosts each of its values reaches, as read in the server's source, and
    an argument that names somewhere else of the model's choosing, if the tool takes one."""

    properties: Mapping[str, str] = field(default_factory=dict[str, str])
    """The argument of each tool that sets an object's properties by name, whose names are held
    to plain ones: none starting with `_`, and none of `UNSET` (an expression, a proxy)."""

    token: str | None = None
    """The variable the server reads the add-on's token from, if the add-on takes one."""

    env: Mapping[str, str] = field(default_factory=dict[str, str])
    """What the server is always given in its environment."""

    ports: bool = False
    """Whether the server takes the app's port as `--port`, as well as its host as `--host`."""

    def __post_init__(self) -> None:
        if not (self.app.isascii() and self.app.isalpha() and self.app.islower()):
            raise ValueError(f"an app is a lowercase name, not {self.app!r}")
        coded = {name for name, tool in self.tools.items() if tool.risk == "code"}
        if wrong := sorted(set(self.code) ^ coded):
            raise ValueError(f"each code tool, and only one, names its code: {', '.join(wrong)}")
        fetching = {name for name, tool in self.tools.items() if tool.risk == "network"}
        if wrong := sorted(set(self.reaches) ^ fetching):
            raise ValueError(f"each network tool, and only one, says where: {', '.join(wrong)}")

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
    version="freecad-mcp==0.1.27",
    reported_version="",
    tools=MappingProxyType(
        {
            "list_documents": Vetted(
                "read", "7063c78dcd515bbcd51703bd321792872200fa8a2a21d764af0c029e0780c951"
            ),
            "get_objects": Vetted(
                "read", "4c2c83c279817d926dc4f0cd2df2ef506f3d1016d2fbcc32116159a1be661026"
            ),
            "get_object": Vetted(
                "read", "64314e6b2afca29596cc9b12d39396d9249e71f8879b5e12417fce05d0718a5b"
            ),
            "get_parts_list": Vetted(
                "read", "7255537e2c0d06926882f97bf6afa3be7818711e4f4858e5c3457a2927a5bdac"
            ),
            "get_view": Vetted(
                "read", "dc7c99aa6729c34018ab259a395b8511dbe85ad7213e203abbebd981a28c5a06"
            ),
            "get_rpc_status": Vetted(
                "read", "3b517f7367fe79fc0fe025e3521075ff0abe00d81d085c9da8d25d8381f8a713"
            ),
            "get_async_status": Vetted(
                "read", "ab00bd59279ceeccefaa8cdf1756af20af73b8f0d93a0d1ec76e93b428ff6962"
            ),
            # The edits, read in the add-on's source at v0.1.27 (rpc_server.py, object_factory.py,
            # property_mapper.py): a document's name, an object's type (`doc.addObject`, or one of
            # FEM's `ObjectsFem.make*`), and its properties, set with `setattr` on the object and
            # on its `ViewObject` by any name, those not in its `PropertiesList` too. None runs
            # `exec` or `eval` itself, but a name is anything: a dunder, or `ExpressionEngine`,
            # which sets expressions as `setExpression` does. So the names are held to plain
            # ones (`properties`, below). `exec` is only in `execute_code` and
            # `execute_code_async`, which are `code`.
            "create_document": Vetted(
                "edit", "e14a671226faa889ab939083e6462cd645090b3b317ed5f6712d97a4b7104c00"
            ),
            "create_object": Vetted(
                "edit", "a214acc079fc7f78dc5c2a30fdd380093a8957f812859b1db4e32eeccea1f936"
            ),
            "edit_object": Vetted(
                "edit", "55ecb3a330350db2046bd1c0182b3af9335ef92911d4a60ed65be2e365f2c868"
            ),
            "delete_object": Vetted(
                "edit", "d9e8b0296af4a958932ebcdd1fdc4028211bc8dc00ece0b2161ff8d7442dc9fd"
            ),
            "execute_code": Vetted(
                "code", "a1817e33675e73a449a0d78d45237e0e74ea4daba669cb8494d80ef056182e20"
            ),
            "execute_code_async": Vetted(
                "code", "1d120340936308e02c815ff497a0cbb42336b15c7e7eb745af44fda27bb22d6e"
            ),
            # A fresh FreeCAD on the runner's machine, not the operator's.
            "execute_code_headless": Vetted(
                "host", "f54beef639c40dfa213d4565d09a84b1d8dfa78317f41358c95fb7c385b92cf5"
            ),
            # Reopen a document from, or copy a part in from, the runner's disk.
            "reload_document": Vetted(
                "host", "d6b38dc6375e621f12c8e4a8eb1bb1150162ca0ca46ff401da0172ebfbcb776c"
            ),
            "insert_part_from_library": Vetted(
                "host", "0c9adfd8243c3100d07e6b9e47097d627c8066b10e9649f2d6d0f7a9a2c50d74"
            ),
            # Starts a solver on the runner's machine.
            "run_fem_analysis": Vetted(
                "host", "9eb4b96f5bd71b3dacf378cb23d3d745646bd54afc8da0047b9a2c0956bffb66"
            ),
        }
    ),
    code=MappingProxyType({"execute_code": "code", "execute_code_async": "code"}),
    properties=MappingProxyType(
        {"create_object": "obj_properties", "edit_object": "obj_properties"}
    ),
    token="FREECAD_MCP_TOKEN",
)
"""neka-nat's FreeCAD server: an add-on's XML-RPC server in FreeCAD's window, on port 9875."""

_LIBRARIES: Final = MappingProxyType(
    {
        "polyhaven": "Poly Haven: api.polyhaven.com, and its files from cdn.polyhaven.com",
        "sketchfab": (
            "Sketchfab: api.sketchfab.com, and its files from the signed download addresses the"
            " API gives, on hosts Sketchfab chooses"
        ),
        "polypizza": "Poly Pizza: api.poly.pizza, and its files from the hosts the API names",
    }
)
_GENERATORS: Final = MappingProxyType(
    {
        "hyper3d": (
            "Hyper3D Rodin: hyperhuman.deemos.com or fal.ai's queue.fal.run, and the model from"
            " the address it answers with"
        ),
        "hunyuan3d": (
            "Hunyuan3D: ai3d.tencentcloudapi.com, and the model from the address it answers with"
        ),
        "meshy": "Meshy: api.meshy.ai, and the model from the address it answers with",
        "auto": (
            "whichever generator the add-on has set up (Hyper3D Rodin, Hunyuan3D or Meshy), and"
            " the model from the address it answers with"
        ),
    }
)
_IMAGE: Final = (
    "image",
    "with `image`, the generator is sent that image: a file it reads on your machine by its path,"
    " or an address it fetches from anywhere",
)
"""generate_3d's `image`: a path or any http(s) address, which the add-on reads or fetches."""

BLENDER: Final = ConnectedServer(
    app="blender",
    title="Blender",
    source="https://github.com/ahujasid/blender-mcp",
    version="mcp-for-blender==2.2.2",
    reported_version="1.30.0",
    tools=MappingProxyType(
        {
            "get_scene_info": Vetted(
                "read", "b18eb1eebf7972d27ad9aa600fabbe692496095beac26a9f52a5fe650baba156"
            ),
            "get_addon_status": Vetted(
                "read", "65e6378d1dbb792dcd83097fd7ff4fd97b37a3828769f34d0bd55bf56fdd5680"
            ),
            "look": Vetted(
                "read", "ca94c06a85727714a0c0b5a6c30acb06e9176e94212cae55504b2691a38b1e44"
            ),
            "execute_blender_code": Vetted(
                "code", "94e43ecf9f7d861ee709cb5b5ba8bf58dde25e0420985ebf8fd04477b8efa784"
            ),
            "search_assets": Vetted(
                "network", "ecc65dae1a069d4bd00eeb30d0965f90486e5b49fa9be3e8f3b3b96937493fbf"
            ),
            "import_asset": Vetted(
                "network", "71f00a7edc8934ee3c186bd3c199d664765d6ce3794a669c3abbbd7789def5de"
            ),
            "generate_3d": Vetted(
                "network", "da28f6bd8f9a6004277bdc9f99f9fc5ce093197e080012c326140a47b91746c7"
            ),
            # What the server's maker collects: not the agent's to change.
            "disable_telemetry": Vetted(
                "host", "fb9daf4cb5fe5945e843e7fe462f8e354db0b127e273f3129f026e2c29e5d810"
            ),
            "record_trajectory_feedback": Vetted(
                "host", "43aaa752d42c245ab57f3ecbcb562d377fa2549fcaa5aa41c6147cf976895ce7"
            ),
        }
    ),
    code=MappingProxyType({"execute_blender_code": "code"}),
    # Read in the server's and the add-on's source at 2.2.2 (src/blender_mcp/server.py, addon.py).
    reaches=MappingProxyType(
        {
            "search_assets": ("source", _LIBRARIES, None),
            "import_asset": ("source", _LIBRARIES, None),
            "generate_3d": ("provider", _GENERATORS, _IMAGE),
        }
    ),
    env=MappingProxyType({"DISABLE_TELEMETRY": "true"}),
    ports=True,
)
"""ahujasid's Blender server: an add-on's socket in Blender, on port 9876, with no token, sending
no telemetry."""
