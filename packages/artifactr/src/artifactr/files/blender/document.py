"""What the adapter reads from a Blender file before Blender starts, and what it gives Blender.

A `.blend` is Blender's memory written out: a header, then blocks, each a head (its code, the
index of its struct in the file's own catalogue of structs, `DNA1`, the address it had, its length
and its count) and its bytes, to `ENDB`; Blender compresses the whole with zstd by default. Blender
reads a block through a pointer by checking its size alone, not its struct, so a file can make a
block of the right size be read as another struct.

[`scan`][artifactr.files.blender.scan] inflates the file against the limit and refuses one that
isn't written by the pinned release's header, versions and catalogue. It refuses a block whose code
or struct is outside the allowed sets below, which fail closed, or whose code and struct disagree.
It reads every pointer of every allowed struct by its declared kind (a struct, a list, `void *`, an
array of pointers, plain data, runtime state) and refuses one that resolves, in the maps Blender
resolves it in, to a block it may not be; and it refuses a node other than those the corpus holds,
and a script node's name anywhere. So a text, a driver, a link to another file, an image, a packed
file and any animation are refused before Blender starts. A raw block's bytes are read only where
an allowed struct's array of pointers points at them. The work is counted, and a file that would
take more is refused as too large. Blender is never given the bytes it was sent: it is given the
blocks the scan read, uncompressed, without the thumbnail, in a file the scan writes (native files
ADR-0015).
"""

import hashlib
import io
import math
import re
import struct
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import cache
from typing import Final, Literal

import zstandard

from artifactr.files.app import AppFailed

HEADER: Final = b"BLENDER17-01v0502"
"""The header Blender 5.2 writes: its format's (`17` bytes of header, format `01`, little-endian
and 8-byte pointers) and its file version, `0502`. Any other is refused."""

HEAD: Final = struct.Struct("<4siQqq")
"""A block's head, as Blender 5.2 writes it: its code, its struct's index, its address, its length
and its count."""

DNA: Final = "73b82b7c7731f18e31c13d75d27fb3f37bdf2f0532f459449c34de864d82550b"
"""The SHA-256 of Blender 5.2's catalogue of structs, `DNA1`, which every file it saves holds: a
file with another is refused, so the structs Blender reads are its own, as it wrote them."""

ZSTD: Final = b"\x28\xb5\x2f\xfd"
GZIP: Final = b"\x1f\x8b"

BLOCKS: Final = 200_000
"""The most blocks a file may hold."""

RAW: Final = 0
"""The struct index of raw data: bytes that aren't a struct, such as a mesh's attributes."""

SPECIAL: Final = frozenset({b"GLOB", b"DNA1", b"REND", b"TEST", b"DATA"})
"""The codes of blocks that aren't a data-block, `ENDB` aside."""

THUMBNAIL: Final = b"TEST"

STAMPS: Final = {
    "FileGlobal": (b"filename",),
    "FileSelectParams": (b"dir",),
    "CurveProfile": (b"changed_timestamp",),
}
"""The fields each save writes anew, which a fingerprint leaves out: the file's path, the folder
the file browser last showed, which is the file's, and a counter of a profile's changes."""

CODES: Final = frozenset({
    b"CA\0\0", b"GR\0\0", b"LA\0\0", b"MA\0\0", b"ME\0\0", b"OB\0\0", b"SC\0\0",
    b"SN\0\0", b"WM\0\0", b"WS\0\0",
})  # fmt: skip
"""The data-blocks a file may hold: cameras, collections, lights, materials, meshes, objects and
scenes, and the window manager, screens and workspaces every file Blender saves holds."""

REFUSED: Final = {
    b"TX\0\0": "a text, which may be a script",
    b"LI\0\0": "a link to another file",
    b"IM\0\0": "an image, which may name a file or be packed",
    b"VF\0\0": "a font, which may name a file",
    b"SO\0\0": "a sound, which may name a file",
    b"MC\0\0": "a movie clip, which names a file",
    b"CF\0\0": "a cache file, which names a file",
    b"VO\0\0": "a volume, which may name a file",
    b"AC\0\0": "an action, an animation",
    b"NT\0\0": "a node group",
}
"""Why some of the data-blocks outside `CODES` are refused, for a clearer refusal."""

STRUCTS: Final = frozenset({
    "ARegion", "ArrayModifierData", "AssetShelf", "AssetShelfSettings", "AssetWeakReference",
    "Attribute", "AttributeArray", "AttributeSingle", "Base", "BevelModifierData", "Camera",
    "Collection", "CollectionChild", "CollectionObject", "ConsoleLine", "CurveMapPoint",
    "CurveMapping", "CurveProfile", "CurveProfilePoint", "Editing", "FileGlobal",
    "FileSelectParams", "FreestyleLineSet", "GpPaint", "GpSculptPaint", "GpVertexPaint",
    "GpWeightPaint", "IDProperty", "IDViewerPathElem", "Lamp", "LayerCollection", "Material",
    "Mesh", "MeshAutomaskingSettings", "MirrorModifierData", "Object", "RegionAssetShelf",
    "RegionView3D", "Scene", "SceneRenderView", "ScrArea", "ScrEdge", "ScrGlobalAreaData",
    "ScrVert", "Sculpt", "SeqTimelineChannel", "SequencerToolSettings", "SolidifyModifierData",
    "SpaceAction", "SpaceButs", "SpaceConsole", "SpaceFile", "SpaceImage", "SpaceInfo",
    "SpaceNode", "SpaceOops", "SpaceSpreadsheet", "SpaceStatusBar", "SpaceText", "SpaceTopBar",
    "SpreadsheetColumn", "SpreadsheetColumnID", "SpreadsheetTable", "SpreadsheetTableIDGeometry",
    "Stereo3dFormat", "SubsurfModifierData", "ToolSettings", "VPaint", "View3D", "ViewLayer",
    "WorkSpace", "WorkSpaceDataRelation", "WorkSpaceInstanceHook", "WorkSpaceLayout", "bNode",
    "bNodeLink", "bNodePanelState", "bNodeSocket", "bNodeSocketValueBoolean",
    "bNodeSocketValueFloat", "bNodeSocketValueRGBA", "bNodeSocketValueVector", "bNodeTree",
    "bNodeTreePath",
    "bScreen", "uiList", "uiViewStateLink", "wmWindow", "wmWindowManager",
})  # fmt: skip
"""The structs a block may be: those Blender 5.2 saves for what its commands and its corpus make.
A struct pointed at from one of these must be one of these too, or the pointer null."""

NAMED: Final = {
    "AnimData": "animation or a driver, which may run Python",
    "ChannelDriver": "a driver, which may run Python",
    "FCurve": "animation or a driver, which may run Python",
    "PackedFile": "a packed file",
    "Library": "a link to another file",
    "Text": "a text, which may be a script",
    "Image": "an image, which may name a file or be packed",
    "NodeShaderScript": "a script node",
    "FreestyleModuleConfig": "a Freestyle module, which runs a script",
}
"""Why some of the structs outside `STRUCTS` are refused, for a clearer refusal."""

REPEATED: Final = frozenset({"SpaceLink"})
"""The structs whose fields others repeat first, by name, rather than embed: every space repeats
`SpaceLink`'s, so a pointer at a `SpaceLink` points at a space."""

DATA_BLOCKS: Final = {
    ("Object", "data"): frozenset({"Mesh", "Camera", "Lamp"}),
    ("Collection", "owner_id"): frozenset({"Scene"}),
    ("bNodeTree", "owner_id"): frozenset({"Material", "Lamp"}),
    ("IDViewerPathElem", "id"): frozenset({"Object"}),
    ("SpaceAction", "ads.source"): frozenset({"Scene"}),
    ("SpaceNode", "id"): frozenset({"Scene"}),
    ("SpaceNode", "from"): frozenset({"Object"}),
}
"""The pointers at any data-block, `ID *`, that Blender 5.2 saved for the commands and the corpus,
each by its struct and its field, and the data-blocks it may point at: any other is null. Blender
reads such a pointer as whatever its context says, an object's data by the object's type."""

OBJECTS: Final = {0: None, 1: "Mesh", 10: "Lamp", 11: "Camera"}
"""The objects' types the commands make, by Blender's number, and the data-block each one's data
is: an empty's none, a mesh's a mesh, a light's a light and a camera's a camera."""

KINDS: Final = {
    b"CA\0\0": "Camera", b"GR\0\0": "Collection", b"LA\0\0": "Lamp", b"MA\0\0": "Material",
    b"ME\0\0": "Mesh", b"OB\0\0": "Object", b"SC\0\0": "Scene", b"SN\0\0": "bScreen",
    b"WM\0\0": "wmWindowManager", b"WS\0\0": "WorkSpace", b"GLOB": "FileGlobal",
}  # fmt: skip
"""The struct of each code's block: a block whose struct isn't its code's is refused. `REND` and
`TEST` are raw data."""

EMBEDDED: Final = {
    "bNodeTree": frozenset({b"MA\0\0", b"LA\0\0"}),
    "Collection": frozenset({b"SC\0\0"}),
}
"""The data-blocks one may embed, as data of its own, and the data-blocks that embed each: a
material's or a light's node tree, a scene's own collection. A data block of any other struct that
begins with an `ID` is refused."""

VERSIONS: Final = (45, 405, 85)
"""The subversion, and the oldest version and subversion able to read it, that 5.2.2 writes in
`FileGlobal`: another is refused, so none of Blender's code for older files runs."""

NODES: Final = {
    "ShaderNodeBsdfPrincipled": 193, "ShaderNodeOutputMaterial": 124,
    "ShaderNodeEmission": 140, "ShaderNodeOutputLight": 126,
}  # fmt: skip
"""The nodes a material's or a light's tree may hold, by their name, with the number each one's
`type` holds: those Blender 5.2.2 makes for a new material or light."""

LISTS: Final = {
    ("ARegion", "ui_lists"): {"uiList"}, ("ARegion", "view_states"): {"uiViewStateLink"},
    ("Collection", "children"): {"CollectionChild"},
    ("Collection", "gobject"): {"CollectionObject"},
    ("Editing", "channels"): {"SeqTimelineChannel"}, ("IDProperty", "data.group"): {"IDProperty"},
    ("LayerCollection", "layer_collections"): {"LayerCollection"},
    ("Object", "modifiers"): {
        "ArrayModifierData", "BevelModifierData", "MirrorModifierData", "SolidifyModifierData",
        "SubsurfModifierData",
    },
    ("RegionAssetShelf", "shelves"): {"AssetShelf"},
    ("Scene", "r.views"): {"SceneRenderView"}, ("Scene", "view_layers"): {"ViewLayer"},
    ("ScrArea", "regionbase"): {"ARegion"},
    ("ScrArea", "spacedata"): {
        "SpaceAction", "SpaceButs", "SpaceConsole", "SpaceFile", "SpaceImage", "SpaceInfo",
        "SpaceNode", "SpaceOops", "SpaceSpreadsheet", "SpaceStatusBar", "SpaceText",
        "SpaceTopBar", "View3D",
    },
    ("SpaceConsole", "history"): {"ConsoleLine"}, ("SpaceNode", "regionbase"): {"ARegion"},
    ("SpaceNode", "treepath"): {"bNodeTreePath"},
    ("SpaceSpreadsheet", "geometry_id.viewer_path.path"): {"IDViewerPathElem"},
    ("SpreadsheetTableIDGeometry", "viewer_path.path"): {"IDViewerPathElem"},
    ("ViewLayer", "freestyle_config.linesets"): {"FreestyleLineSet"},
    ("ViewLayer", "layer_collections"): {"LayerCollection"},
    ("ViewLayer", "object_bases"): {"Base"},
    ("WorkSpace", "hook_layout_relations"): {"WorkSpaceDataRelation"},
    ("WorkSpace", "layouts"): {"WorkSpaceLayout"},
    ("bNode", "inputs"): {"bNodeSocket"}, ("bNode", "outputs"): {"bNodeSocket"},
    ("bNodeTree", "links"): {"bNodeLink"}, ("bNodeTree", "nodes"): {"bNode"},
    ("bScreen", "areabase"): {"ScrArea"}, ("bScreen", "edgebase"): {"ScrEdge"},
    ("bScreen", "vertbase"): {"ScrVert"},
    ("wmWindow", "global_area_map.areabase"): {"ScrArea"},
    ("wmWindow", "global_area_map.edgebase"): {"ScrEdge"},
    ("wmWindow", "global_area_map.vertbase"): {"ScrVert"},
    ("wmWindowManager", "windows"): {"wmWindow"},
    # Not lists, but `void *`, read as whatever their context says.
    ("ARegion", "regiondata"): {"RegionAssetShelf", "RegionView3D"},
    ("Attribute", "data"): {"AttributeArray", "AttributeSingle"},
    ("AttributeArray", "data"): {None}, ("AttributeSingle", "data"): {None},
    ("IDProperty", "data.pointer"): {None},
    ("WorkSpaceDataRelation", "parent"): {"WorkSpaceInstanceHook"},
    ("WorkSpaceDataRelation", "value"): {"WorkSpaceLayout"},
    ("bNodeSocket", "default_value"): {
        "bNodeSocketValueBoolean", "bNodeSocketValueFloat", "bNodeSocketValueRGBA",
        "bNodeSocketValueVector",
    },
}  # fmt: skip
"""Each list, `ListBase`, and each `void *` that Blender 5.2.2 saved for the commands and the
corpus, by its struct and its field, and the structs its first and last, or it, may point at
(`None` for raw data). Blender reads each by its context, so any other must point at no block:
a Freestyle module's list, a node's storage, a property's data-block."""

SCRIPT_NODES: Final = (b"ShaderNodeScript", b"NodeShaderScript")
"""A script node's names, which Cycles compiles from a text or a file: refused in any block's
bytes, whatever struct the block claims to be."""

LIMIT: Final = 256 << 20
"""The most bytes a file may inflate to, by default. A scan holds the file sent, its inflated
bytes and the file it writes at once: about three times this, at its peak."""

WORK: Final = 4_000_000
"""The most records and pointers a scan reads, past which a file is refused as too large: about
1.3 seconds of the densest records on an Apple M-series core, where a scene of every command
takes about 12,500."""

CHUNK: Final = 1 << 20
ARRAY: Final = re.compile(rb"\[(\d+)\]")


PRIMITIVES: Final = frozenset({
    "char", "uchar", "short", "ushort", "int", "uint", "float", "double", "bool", "int8_t",
    "uint8_t", "int16_t", "uint16_t", "int32_t", "uint32_t", "int64_t", "uint64_t",
})  # fmt: skip
"""Plain data a pointer may point at: only at raw data."""

Kind = Literal["struct", "array", "list", "void", "plain", "runtime"]
"""What a pointer field points at: a struct, `T *`; an array of pointers, `T **`, raw data whose
each eight bytes point at a `T`; a list's first or last, `ListBase`; anything, `void *`; plain data,
`char *`; or what the catalogue doesn't name, such as runtime state or a function, which only
Blender's own code fills, and which must point at no block."""


@dataclass(frozen=True)
class Slot:
    """A pointer field of a struct, or of a struct it holds, and what it may point at."""

    offset: int
    path: str
    """Its field's path, such as `ads.source`."""
    kind: Kind
    pointed: str
    """The struct, or the type, it points at."""


@dataclass(frozen=True)
class Scanned:
    """A file that may be opened: what Blender is given, and whether it came compressed."""

    content: bytes
    """The blocks the scan read, in their order, uncompressed, without the thumbnail."""

    compressed: bool
    """Whether the file was compressed, as a save keeps it."""


@dataclass(frozen=True)
class Block:
    """A block of a file: its code, its struct's index and count, and where it is."""

    code: bytes
    index: int
    count: int
    address: int
    """Where it was in Blender's memory, by which other blocks point at it."""
    start: int
    """Where its head starts in the file's bytes."""
    end: int
    """Where its bytes end."""

    @property
    def bytes_start(self) -> int:
        """Where its bytes start, after its head."""
        return self.start + HEAD.size


@dataclass(frozen=True)
class Blend:
    """A file read: its bytes, uncompressed, its blocks to `ENDB`, and its catalogue of structs."""

    data: bytes
    compressed: bool
    blocks: list[Block]
    catalogue: "Catalogue"


def read(content: bytes, limit: int = LIMIT) -> Blend:
    """A file's blocks and catalogue, refused if it isn't one Blender 5.2 wrote.

    Raises:
        AppFailed: `refused` if its header, a block's head or its catalogue isn't Blender 5.2's;
            `too_large` if it inflates past the limit.
    """
    data, compressed = _inflated(content, limit)
    blocks = _blocks(data)
    return Blend(data, compressed, blocks, _catalogue(data, blocks))


def scan(content: bytes, limit: int = LIMIT, work: int = WORK) -> Scanned:
    """Refuse what isn't a Blender 5.2 file, or holds what isn't allowed, and write it again.

    Raises:
        AppFailed: `refused` if it isn't a file Blender 5.2 wrote, or holds a block, a struct or
            a pointer that isn't allowed; `too_large` if it inflates past the limit, or would take
            more than `work` records and pointers to read.
    """
    blend = read(content, limit)
    _Scan(blend, work).check()
    kept = (block for block in blend.blocks if block.code != THUMBNAIL)
    return Scanned(HEADER + b"".join(blend.data[b.start : b.end] for b in kept), blend.compressed)


def fingerprint(content: bytes, limit: int = LIMIT) -> str:
    """The SHA-256 of a file's blocks, uncompressed, without its thumbnail and what a save stamps.

    Blender writes each pointer as an id it derives from its data-block's name, not the address it
    had, so the same scene's blocks are the same bytes in any process; but each save writes the
    file's own path, which is a call's directory, and a counter, `STAMPS`. So two saves in a row of
    the same scene, in two calls, have the same fingerprint, compressed or not.
    """
    blend = read(content, limit)
    catalogue = blend.catalogue
    stamped = {
        index: [catalogue.field(index, name) for name in names]
        for struct_name, names in STAMPS.items()
        for index in [catalogue.index(struct_name)]
    }
    digest = hashlib.sha256(HEADER)
    for block in blend.blocks:
        if block.code == THUMBNAIL:
            continue
        written = bytearray(blend.data[block.start : block.end])
        for each in range(block.count) if block.index in stamped else ():
            for offset, length in stamped[block.index]:
                at = HEAD.size + each * catalogue.size(block.index) + offset
                written[at : at + length] = bytes(length)
        digest.update(written)
    return digest.hexdigest()


def _inflated(content: bytes, limit: int) -> tuple[bytes, bool]:
    """The file's bytes, inflated a chunk at a time if compressed, refused past the limit."""
    if content.startswith(GZIP):
        raise AppFailed(
            "refused", "not a Blender 5.2 file: compressed with gzip, by a Blender before 3.0"
        )
    if not content.startswith(ZSTD):
        if len(content) > limit:
            raise AppFailed("too_large", f"the file is larger than {limit} bytes")
        return content, False
    chunks: list[bytes] = []
    read = 0
    try:
        with zstandard.ZstdDecompressor().stream_reader(
            io.BytesIO(content), read_across_frames=True
        ) as stream:
            while chunk := stream.read(CHUNK):
                read += len(chunk)
                if read > limit:
                    raise AppFailed("too_large", f"the file inflates past {limit} bytes")
                chunks.append(chunk)
    except zstandard.ZstdError:
        raise AppFailed("refused", "not a Blender file: its zstd doesn't inflate") from None
    return b"".join(chunks), True


def _blocks(data: bytes) -> list[Block]:
    """The file's blocks, to `ENDB`, refused if its header isn't 5.2's, or a head lies."""
    if not data.startswith(b"BLENDER"):
        raise AppFailed("refused", "not a Blender file")
    if not data.startswith(HEADER):
        # A header of 12 bytes names the pointers' size and the byte order of Blender before 5.0.
        raise AppFailed("refused", f"not a Blender 5.2 file: its header is {data[: len(HEADER)]!r}")
    blocks: list[Block] = []
    at = len(HEADER)
    while True:
        if len(blocks) >= BLOCKS:
            raise AppFailed("refused", f"the file holds more than {BLOCKS} blocks")
        if at + HEAD.size > len(data):
            raise AppFailed("refused", "the file ends before its last block")
        code, index, address, length, count = HEAD.unpack_from(data, at)
        end = at + HEAD.size + length
        if length < 0 or count < 0 or end > len(data):
            raise AppFailed("refused", f"a {code!r} block's head lies about its size")
        blocks.append(Block(code, index, count, address, at, end))
        at = end
        if code == b"ENDB":
            break
    if at != len(data):
        raise AppFailed("refused", "the file holds bytes after its end")
    return blocks


def _catalogue(data: bytes, blocks: list[Block]) -> "Catalogue":
    """The file's catalogue of structs, refused unless it is Blender 5.2's own."""
    found = [block for block in blocks if block.code == b"DNA1"]
    if len(found) != 1:
        raise AppFailed("refused", "the file doesn't hold one catalogue of structs")
    payload = data[found[0].bytes_start : found[0].end]
    if hashlib.sha256(payload).hexdigest() != DNA:
        raise AppFailed("refused", "the file's catalogue of structs isn't Blender 5.2's")
    return _parsed(payload)


@cache
def _parsed(payload: bytes) -> "Catalogue":
    """Blender 5.2's catalogue, read once: its digest is checked before."""
    return Catalogue(payload)


class _Scan:
    """One file's scan: its blocks, the maps Blender resolves its pointers in, and its work.

    Blender resolves a pointer at a data-block in one map of every data-block's address, and a
    pointer at data in a map of the addresses of the data that follows the data-block it belongs
    to, which it clears at each data-block (`read_data_into_datamap`, `newlibadr` in `readfile.cc`).
    The scan builds both, refuses an address twice in either, and holds a pointer to what it
    resolves to in each map it is found in.
    """

    def __init__(self, blend: Blend, work: int) -> None:
        self.data = blend.data
        self.blocks = blend.blocks
        self.catalogue = blend.catalogue
        self.left = work
        self.ids: dict[int, str] = {}
        """Each data-block's address, and its struct."""
        self.scopes: list[dict[int, str | None]] = []
        """The data of each data-block, or other block, by address: its struct, or None if raw."""
        self.owners: list[bytes] = []
        """The code of the block each scope's data follows."""
        self.of: list[int] = []
        """Each block's scope."""
        self.data_blocks: dict[tuple[int, int], Block] = {}
        """Each data block, by its scope and its address."""

    def check(self) -> None:
        for block in self.blocks:
            self._code_and_struct(block)
            self._address(block)
        for block, scope in zip(self.blocks, self.of, strict=True):
            if block.index != RAW and block.code not in {b"DNA1", b"ENDB"}:
                self._records(block, scope)

    def _spend(self, work: int) -> None:
        self.left -= work
        if self.left < 0:
            raise AppFailed("too_large", "the file would take too long to scan")

    def _code_and_struct(self, block: Block) -> None:
        """Refuse a block whose code or struct isn't allowed, or disagree, or a script node."""
        catalogue = self.catalogue
        if block.code not in SPECIAL | CODES | {b"ENDB"}:
            why = REFUSED.get(block.code, "a data-block that isn't allowed")
            raise AppFailed("refused", f"the file holds {why}: {block.code.rstrip(bytes(1))!r}")
        if block.code in {b"DNA1", b"ENDB"}:
            return
        start = block.bytes_start
        if any(self.data.find(name, start, block.end) >= 0 for name in SCRIPT_NODES):
            raise AppFailed("refused", "the file holds a script node")
        if block.index == RAW:
            if block.code in KINDS:
                raise AppFailed("refused", f"a {block.code!r} block is raw data")
            return
        if not 0 < block.index < len(catalogue.structs):
            raise AppFailed("refused", f"a block names struct {block.index}, which isn't one")
        name = catalogue.name(block.index)
        if name not in STRUCTS:
            why = NAMED.get(name, "a struct that isn't allowed")
            raise AppFailed("refused", f"the file holds {why}: {name}")
        if KINDS.get(block.code, name) != name or block.code in {b"REND", b"TEST"}:
            raise AppFailed("refused", f"a {block.code!r} block holds a {name}")
        if block.end - start != catalogue.size(block.index) * block.count:
            raise AppFailed("refused", f"a {name} block's size isn't its count's")

    def _address(self, block: Block) -> None:
        """Map a block's address, refused if it is already mapped where Blender would map it."""
        if block.code in {b"DNA1", b"ENDB"}:
            self.of.append(-1)
            return
        name = None if block.index == RAW else self.catalogue.name(block.index)
        if block.code != b"DATA":
            self.scopes.append({})
            self.owners.append(block.code)
            if block.code in CODES:
                if block.address in self.ids:
                    raise AppFailed("refused", f"two data-blocks are at {block.address:#x}")
                self.ids[block.address] = str(name)
        elif not self.scopes:
            raise AppFailed("refused", "the file holds data before any block it belongs to")
        elif block.address in self.scopes[-1]:
            raise AppFailed("refused", f"two blocks of one data-block's are at {block.address:#x}")
        else:
            self.scopes[-1][block.address] = name
            self.data_blocks[len(self.scopes) - 1, block.address] = block
            if name in self.catalogue.identified and self.owners[-1] not in EMBEDDED.get(
                str(name), frozenset()
            ):
                raise AppFailed("refused", f"a {self.owners[-1]!r} holds a {name} as its data")
        self.of.append(len(self.scopes) - 1)

    def _records(self, block: Block, scope: int) -> None:
        """Refuse a record that points at what its pointers' kinds don't allow."""
        catalogue = self.catalogue
        name = catalogue.name(block.index)
        size = catalogue.size(block.index)
        slots = catalogue.slots(block.index)
        self._spend(block.count * (1 + len(slots)))
        for each in range(block.count):
            record = block.bytes_start + each * size
            for slot in slots:
                (value,) = struct.unpack_from("<Q", self.data, record + slot.offset)
                if value:
                    self._pointer(name, slot, value, scope)
            if name in self.catalogue.records:
                self.catalogue.records[name](self, record, scope)

    def hits(self, value: int, scope: int) -> list[str | None]:
        """What an address resolves to, in each map Blender may resolve it in."""
        hits: list[str | None] = []
        if value in self.scopes[scope]:
            hits.append(self.scopes[scope][value])
        if value in self.ids:
            hits.append(self.ids[value])
        return hits

    def _pointer(self, name: str, slot: Slot, value: int, scope: int) -> None:
        hits = self.hits(value, scope)
        where = f"{name}.{slot.path}"
        if slot.kind == "struct":
            if slot.pointed not in self.catalogue.pointable:
                why = NAMED.get(slot.pointed, "a struct that isn't allowed")
                raise AppFailed("refused", f"{where} points at {why}: {slot.pointed}")
            if slot.pointed == "ID":
                allowed: set[str | None] = set(DATA_BLOCKS.get((name, slot.path), ()))
                if not hits or not set(hits) <= allowed:
                    raise AppFailed("refused", f"{where} points at {_named(hits)}, not ID")
                return
            refused = any(slot.pointed not in self.catalogue.begins(hit) for hit in hits)
        elif slot.kind in {"list", "void"}:
            allowed = set(LISTS.get((name, slot.path), ()))
            refused = not set(hits) <= allowed
        elif slot.kind == "array":
            refused = hits != [None] if hits else False
            if not refused and hits:
                self._array(where, slot.pointed, value, scope)
        elif slot.kind == "plain":
            refused = not set(hits) <= {None}
        else:
            refused = bool(hits)
        if refused:
            raise AppFailed("refused", f"{where} points at {_named(hits)}, not {slot.pointed}")

    def _array(self, where: str, pointed: str, value: int, scope: int) -> None:
        """Refuse an array of pointers, raw data, whose pointers point at what isn't a `pointed`."""
        block = self.data_blocks[scope, value]
        entries = (block.end - block.bytes_start) // 8
        self._spend(entries)
        for at in range(entries):
            (entry,) = struct.unpack_from("<Q", self.data, block.bytes_start + 8 * at)
            hits = self.hits(entry, scope) if entry else []
            if any(pointed not in self.catalogue.begins(hit) for hit in hits):
                raise AppFailed("refused", f"{where} holds a pointer at {_named(hits)}")


def _object(scan: _Scan, record: int, scope: int) -> None:
    """Refuse an object of a type the commands don't make, or whose data isn't its type's."""
    kind_at, data_at = scan.catalogue.object_fields
    (kind,) = struct.unpack_from("<h", scan.data, record + kind_at)
    (held,) = struct.unpack_from("<Q", scan.data, record + data_at)
    if kind not in OBJECTS:
        raise AppFailed("refused", f"the file holds an object of type {kind}, which isn't allowed")
    if (scan.hits(held, scope) if held else [None]) != [OBJECTS[kind]]:
        raise AppFailed("refused", f"an object of type {kind} holds data of another type")


def _node(scan: _Scan, record: int, _: int) -> None:
    """Refuse a node other than those `NODES` names, or whose number isn't its name's."""
    (name_at, name_size), type_at = scan.catalogue.node_fields
    idname = scan.data[record + name_at : record + name_at + name_size].split(b"\0")[0]
    (kind,) = struct.unpack_from("<h", scan.data, record + type_at)
    if NODES.get(idname.decode(errors="replace")) != kind:
        raise AppFailed("refused", f"the file holds a node that isn't allowed: {idname!r} ({kind})")


def _globals(scan: _Scan, record: int, _: int) -> None:
    """Refuse a file whose versions aren't those 5.2.2 writes."""
    found = tuple(
        struct.unpack_from("<h", scan.data, record + at)[0] for at in scan.catalogue.versions
    )
    if found != VERSIONS:
        raise AppFailed("refused", f"not a Blender 5.2 file: its versions are {found}")


def _named(hits: list[str | None]) -> str:
    """What an address resolves to, for a refusal."""
    return " and ".join("raw data" if hit is None else hit for hit in hits) or "no block"


class Catalogue:
    """Blender's catalogue of structs, `DNA1`: its names, its types and their sizes, its structs."""

    def __init__(self, payload: bytes) -> None:
        # Its digest is Blender 5.2's, checked before: these are bytes Blender wrote.
        self.names, at = _strings(payload, 4)
        self.types, at = _strings(payload, at)
        self.sizes = struct.unpack_from(f"<{len(self.types)}h", payload, at + 4)
        at = (at + 4 + 2 * len(self.types) + 3) & ~3
        (count,) = struct.unpack_from("<i", payload, at + 4)
        at += 8
        self.structs: list[tuple[int, tuple[tuple[int, int], ...]]] = []
        for _ in range(count):
            kind, fields = struct.unpack_from("<hh", payload, at)
            pairs = struct.unpack_from(f"<{2 * fields}h", payload, at + 4)
            self.structs.append((kind, tuple(zip(pairs[::2], pairs[1::2], strict=True))))
            at += 4 + 4 * fields
        self.by_type = {kind: index for index, (kind, _) in enumerate(self.structs)}
        self._slots: dict[int, tuple[Slot, ...]] = {}
        self._begins: dict[str, frozenset[str]] = {}
        self.pointable = {*REPEATED, *(base for name in STRUCTS for base in self.begins(name))}
        """The structs a pointer may name: those allowed, and those one of them begins with."""
        self.identified = frozenset(name for name in STRUCTS if "ID" in self.begins(name))
        """The allowed structs that are data-blocks: those that begin with an `ID`."""
        objects = self.index("Object")
        self.object_fields = (self.field(objects, b"type")[0], self.field(objects, b"data")[0])
        nodes = self.index("bNode")
        self.node_fields = (self.field(nodes, b"idname"), self.field(nodes, b"type")[0])
        globals_ = self.index("FileGlobal")
        self.versions = tuple(
            self.field(globals_, name)[0]
            for name in (b"subversion", b"minversion", b"minsubversion")
        )
        self.records: dict[str, Callable[[_Scan, int, int], None]] = {
            "Object": _object, "bNode": _node, "FileGlobal": _globals,
        }  # fmt: skip
        """What else each record of a struct is held to, beside its pointers."""

    def name(self, index: int) -> str:
        """A struct's name, by its index."""
        return self.types[self.structs[index][0]].decode()

    def size(self, index: int) -> int:
        """A struct's size in bytes, by its index."""
        return self.sizes[self.structs[index][0]]

    def fields(self, index: int) -> list[tuple[int, int, bytes, int]]:
        """Each field of a struct: its offset, its type, its name, and its size."""
        found: list[tuple[int, int, bytes, int]] = []
        offset = 0
        for kind, name in self.structs[index][1]:
            field = self.names[name]
            count = math.prod(int(n) for n in ARRAY.findall(field))
            each = 8 if field.startswith((b"*", b"(*")) else self.sizes[kind]
            found.append((offset, kind, field, each * count))
            offset += each * count
        return found

    def index(self, name: str) -> int:
        """A struct's index, by its name."""
        return self.by_type[self.types.index(name.encode())]

    def field(self, index: int, name: bytes) -> tuple[int, int]:
        """A field's offset and size, by its name, without its stars and brackets."""
        return next(
            (offset, size)
            for offset, _, field, size in self.fields(index)
            if field.lstrip(b"*").split(b"[")[0] == name
        )

    def begins(self, name: str | None) -> frozenset[str]:
        """The structs a block of a struct may be read as, through a pointer.

        Itself, the struct it embeds first, as Blender's structs inherit (an `ID`, a
        `ModifierData`), and so on, and any of `REPEATED` whose fields it repeats first. Raw data,
        `None`, is none.
        """
        if name is None:
            return frozenset()
        if name not in self._begins:
            self._begins[name] = self._began(name)
        return self._begins[name]

    def _began(self, name: str) -> frozenset[str]:
        found = {name}
        index: int | None = self.index(name)
        while index is not None and (fields := self.structs[index][1]):
            kind, first = fields[0]
            if self.names[first].startswith((b"*", b"(")):
                break
            found.add(self.types[kind].decode())
            index = self.by_type.get(kind)
        own = [field for _, _, field, _ in self.fields(self.index(name))]
        for repeated in REPEATED:
            heads = [field for _, _, field, _ in self.fields(self.index(repeated))]
            if own[: len(heads)] == heads:
                found.add(repeated)
        return frozenset(found)

    def slots(self, index: int) -> tuple[Slot, ...]:
        """Each pointer field of a struct, and of each struct it holds, and what it points at."""
        if index not in self._slots:
            self._slots[index] = self._slotted(index)
        return self._slots[index]

    def _slotted(self, index: int) -> tuple[Slot, ...]:
        found: list[Slot] = []
        for offset, kind, field, size in self.fields(index):
            typed = self.types[kind].decode()
            path = field.lstrip(b"*").split(b"[")[0].decode()
            inner = self.by_type.get(kind)
            if field.startswith(b"*"):
                if field.startswith(b"**"):
                    pointer: Kind = "array" if inner is not None else "plain"
                elif inner is not None:
                    pointer = "struct"
                elif typed == "void":
                    pointer = "void"
                else:
                    pointer = "plain" if typed in PRIMITIVES else "runtime"
                found += [Slot(offset + at, path, pointer, typed) for at in range(0, size, 8)]
            elif field.startswith(b"("):
                found += [Slot(offset + at, path, "runtime", typed) for at in range(0, size, 8)]
            elif typed == "ListBase":
                found += [
                    Slot(offset + at + end, path, "list", typed)
                    for at in range(0, size, 16)
                    for end in (0, 8)
                ]
            elif inner is not None:
                found += [
                    replace(slot, offset=offset + at + slot.offset, path=f"{path}.{slot.path}")
                    for at in range(0, size, self.sizes[kind])
                    for slot in self.slots(inner)
                ]
        return tuple(found)


def _strings(payload: bytes, at: int) -> tuple[list[bytes], int]:
    """A counted list of strings, each ended by a zero, and where the next part starts, aligned."""
    (count,) = struct.unpack_from("<i", payload, at + 4)
    at += 8
    found: list[bytes] = []
    for _ in range(count):
        end = payload.index(b"\0", at)
        found.append(payload[at:end])
        at = end + 1
    return found, (at + 3) & ~3
