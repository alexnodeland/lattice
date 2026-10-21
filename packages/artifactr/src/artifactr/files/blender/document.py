"""What the adapter reads from a Blender file before Blender starts, and what it gives Blender.

A `.blend` is Blender's memory written out: a header, then blocks, each a head (its code, the
index of its struct in the file's own catalogue of structs, `DNA1`, the address it had, its length
and its count) and its bytes, to `ENDB`; Blender compresses the whole with zstd by default. Blender
reads a block through a pointer by checking its size alone, not its struct, so a file can make any
block of the right size be read as anything. [`scan`][artifactr.files.blender.scan] inflates the
file against the limit, and refuses one that isn't written by the pinned release's format and
catalogue, holds a block whose code or struct is outside the allowed sets below, which fail closed,
points at a struct outside them from one inside them, or names a script node anywhere; so a text,
a driver, a link to another file, an image, a packed file and any animation are refused before
Blender starts. Blender is never given the bytes it was sent: it is given the blocks the scan read,
uncompressed, without the thumbnail, in a file the scan writes (native files ADR-0015).
"""

import hashlib
import io
import math
import re
import struct
from dataclasses import dataclass
from functools import cache
from typing import Final

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

SCRIPT_NODES: Final = (b"ShaderNodeScript", b"NodeShaderScript")
"""A script node's names, which Cycles compiles from a text or a file: refused in any block's
bytes, whatever struct the block claims to be."""

LIMIT: Final = 256 << 20
"""The most bytes a file may inflate to, by default."""

CHUNK: Final = 1 << 20
ARRAY: Final = re.compile(rb"\[(\d+)\]")


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


def scan(content: bytes, limit: int = LIMIT) -> Scanned:
    """Refuse what isn't a Blender 5.2 file, or holds what isn't allowed, and write it again.

    Raises:
        AppFailed: `refused` if it isn't a file Blender 5.2 wrote, or holds a block, a struct or
            a pointer that isn't allowed; `too_large` if it inflates past the limit.
    """
    blend = read(content, limit)
    for block in blend.blocks:
        _check(blend.data, block, blend.catalogue)
    kept = (block for block in blend.blocks if block.code != THUMBNAIL)
    return Scanned(HEADER + b"".join(blend.data[b.start : b.end] for b in kept), blend.compressed)


def fingerprint(content: bytes, limit: int = LIMIT) -> str:
    """The SHA-256 of a file's blocks, uncompressed, without its thumbnail and what a save stamps.

    Blender writes each block where it was in memory, the same for the same scene; but each save
    writes the file's own path, which is a call's directory, and a counter, `STAMPS`. So two
    saves in a row of the same scene, in two calls, have the same fingerprint, compressed or not.
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


def _check(data: bytes, block: Block, catalogue: "Catalogue") -> None:
    """Refuse a block whose code, struct, size or pointers aren't allowed."""
    if block.code not in SPECIAL | CODES | {b"ENDB"}:
        why = REFUSED.get(block.code, "a data-block that isn't allowed")
        raise AppFailed("refused", f"the file holds {why}: {block.code.rstrip(bytes(1))!r}")
    if block.code in {b"DNA1", b"ENDB"}:
        return
    start = block.bytes_start
    if any(data.find(name, start, block.end) >= 0 for name in SCRIPT_NODES):
        raise AppFailed("refused", "the file holds a script node")
    if block.index == RAW:
        return
    if not 0 < block.index < len(catalogue.structs):
        raise AppFailed("refused", f"a block names struct {block.index}, which isn't one")
    name = catalogue.name(block.index)
    if name not in STRUCTS:
        why = NAMED.get(name, "a struct that isn't allowed")
        raise AppFailed("refused", f"the file holds {why}: {name}")
    size = catalogue.size(block.index)
    if block.end - start != size * block.count:
        raise AppFailed("refused", f"a {name} block's size isn't its count's")
    for each in range(block.count):
        for offset, pointed in catalogue.pointers(block.index):
            if struct.unpack_from("<Q", data, start + each * size + offset)[0]:
                why = NAMED.get(pointed, "a struct that isn't allowed")
                raise AppFailed("refused", f"a {name} points at {why}: {pointed}")


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
        self._pointers: dict[int, tuple[tuple[int, str], ...]] = {}
        self.pointable = {*STRUCTS, "SpaceLink"}
        """The structs a pointer may name: those allowed, and those one of them begins with, as
        Blender's structs inherit, by embedding their base first (an `ID`, a `ModifierData`),
        and `SpaceLink`, the head every space repeats, field by field, rather than embeds."""
        for name in STRUCTS:
            index: int | None = self.index(name)
            while index is not None and (fields := self.structs[index][1]):
                kind, first = fields[0]
                if self.names[first].startswith((b"*", b"(")):
                    break
                self.pointable.add(self.types[kind].decode())
                index = self.by_type.get(kind)

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

    def pointers(self, index: int) -> tuple[tuple[int, str], ...]:
        """Where a struct, and each struct it holds, points at a struct outside `STRUCTS`."""
        if index not in self._pointers:
            self._pointers[index] = self._pointed(index)
        return self._pointers[index]

    def _pointed(self, index: int) -> tuple[tuple[int, str], ...]:
        found: list[tuple[int, str]] = []
        for offset, kind, field, size in self.fields(index):
            pointed = self.types[kind].decode()
            inner = self.by_type.get(kind)
            if inner is None:
                continue
            if field.startswith(b"*") and not field.startswith(b"**"):
                if pointed not in self.pointable:
                    found += [(offset + at, pointed) for at in range(0, size, 8)]
            elif not field.startswith((b"*", b"(")):
                each = self.sizes[kind]
                found += [
                    (offset + at + inner_offset, inner_pointed)
                    for at in range(0, size, each)
                    for inner_offset, inner_pointed in self.pointers(inner)
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
