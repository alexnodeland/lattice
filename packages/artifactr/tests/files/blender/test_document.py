"""What the adapter reads of a Blender file before Blender starts: what it refuses, the file it
writes again, and its fingerprint."""

import struct

import pytest
import zstandard

from artifactr.files.app import AppFailed
from artifactr.files.blender import fingerprint, scan
from artifactr.files.blender.document import (
    HEAD,
    HEADER,
    RAW,
    STRUCTS,
    THUMBNAIL,
    read,
)
from tests.files.corpus.blender.corpus import (
    CORPUS,
    HOSTILE,
    changed,
    first,
    inserted,
    offset_of,
    plain,
    pointed,
    written,
)

SOURCE = CORPUS.source("primitives")


def ended(data: bytearray, code: bytes, index: int, payload: bytes, count: int = 1) -> bytes:
    """A file with a block of its own before its `ENDB`."""
    end = len(data) - HEAD.size
    head = HEAD.pack(code, index, 0x1000, len(payload), count)
    return bytes(data[:end] + head + payload + data[end:])


def index_of(name: str) -> int:
    return read(SOURCE).catalogue.index(name)


def test_a_file_blender_saved_is_written_again_without_its_thumbnail() -> None:
    scanned = scan(SOURCE)
    assert scanned.compressed
    assert scanned.content.startswith(HEADER)
    blend = read(scanned.content)
    assert not blend.compressed
    assert THUMBNAIL in {block.code for block in read(SOURCE).blocks}
    assert THUMBNAIL not in {block.code for block in blend.blocks}
    assert scan(scanned.content).content == scanned.content, "uncompressed, as Blender is given"


@pytest.mark.parametrize("feature", sorted(CORPUS.makers))
def test_every_corpus_file_is_allowed_and_its_fingerprint_kept(feature: str) -> None:
    source = CORPUS.source(feature)
    assert fingerprint(scan(source).content) == fingerprint(source)


def test_a_fingerprint_leaves_out_what_each_save_stamps() -> None:
    def stamped(data: bytearray) -> None:
        _, at = first(data, "FileGlobal")
        offset, _ = read(bytes(data)).catalogue.field(index_of("FileGlobal"), b"filename")
        data[at + offset : at + offset + 9] = b"/tmp/call"

    assert fingerprint(changed("primitives", stamped)) == fingerprint(SOURCE)
    loc, _ = read(SOURCE).catalogue.field(index_of("Object"), b"loc")
    moved = changed(
        "primitives", lambda d: struct.pack_into("<f", d, first(d, "Object")[1] + loc, 9)
    )
    assert fingerprint(moved) != fingerprint(SOURCE), "an object's place is its own"


@pytest.mark.parametrize(
    ("name", "failure", "why"),
    [
        ("text_block", "refused", "a text, which may be a script"),
        ("python_driver", "refused", "animation or a driver, which may run Python: AnimData"),
        ("simple_driver", "refused", "animation or a driver, which may run Python: AnimData"),
        ("animation", "refused", "animation or a driver, which may run Python: AnimData"),
        ("confused_pointer", "refused", "Object.adt points at animation or a driver"),
        ("confused_parent", "refused", "Object.parent points at Camera, not Object"),
        ("confused_data", "refused", "an object of type 10 holds data of another type"),
        ("node_data_block", "refused", "bNode.id points at Object, not ID"),
        ("same_address", "refused", "two blocks of one data-block's are at"),
        ("same_data_block_address", "refused", "two data-blocks are at"),
        ("code_and_struct", "refused", "block holds a Camera"),
        ("embedded_object", "refused", "holds a Object as its data"),
        ("freestyle_module", "refused", "freestyle_config.modules points at Object"),
        ("node_storage", "refused", "bNode.storage points at Object, not void"),
        ("material_array", "refused", "Mesh.mat holds a pointer at Object"),
        ("older_file", "refused", r"its versions are \(45, 257, 85\)"),
        ("image_node", "refused", "a node that isn't allowed: b'ShaderNodeTexImage'"),
        (
            "node_number",
            "refused",
            "a node that isn't allowed: b'ShaderNodeBsdfPrincipled' \\(34\\)",
        ),
        ("dense_records", "too_large", "would take too long to scan"),
        ("library_link", "refused", "a link to another file"),
        ("packed_image", "refused", "an image"),
        ("external_image", "refused", "an image"),
        ("script_node", "refused", "a script node"),
        ("zstd_bomb", "too_large", "inflates past"),
        ("gzip", "refused", "gzip"),
        ("pointer_size", "refused", "its header is b'BLENDER_v405"),
        ("big_endian", "refused", "its header is b'BLENDER-V405"),
        ("another_version", "refused", "its header is b'BLENDER17-01v0503'"),
        ("lying_length", "refused", "lies about its size"),
        ("negative_length", "refused", "lies about its size"),
        ("huge_count", "refused", "size isn't its count's"),
        ("no_struct", "refused", "struct 30000, which isn't one"),
        ("after_the_end", "refused", "bytes after its end"),
        ("another_catalogue", "refused", "isn't Blender 5.2's"),
    ],
)
def test_each_hostile_file_is_refused_before_blender_starts(
    name: str, failure: str, why: str
) -> None:
    with pytest.raises(AppFailed, match=why) as failed:
        scan(HOSTILE[name]())
    assert failed.value.failure == failure


def test_a_parents_cycle_is_left_to_the_script() -> None:
    """A parent is an object, which the scan allows: Blender reads it, and the script refuses."""
    assert scan(HOSTILE["cycle"]())


@pytest.mark.parametrize(
    ("content", "why"),
    [
        (b"", "not a Blender file"),
        (b"PK\x03\x04", "not a Blender file"),
        (b"\x28\xb5\x2f\xfd" + b"\xff" * 16, "its zstd doesn't inflate"),
        (bytes(plain("primitives"))[:-1], "ends before its last block"),
        (HEADER, "ends before its last block"),
    ],
)
def test_what_isnt_a_whole_blender_file_is_refused(content: bytes, why: str) -> None:
    with pytest.raises(AppFailed, match=why):
        scan(content)


def test_a_file_past_the_limit_is_too_large_compressed_or_not() -> None:
    for content in (SOURCE, bytes(plain("primitives"))):
        with pytest.raises(AppFailed, match=r"past|larger") as failed:
            scan(content, 1024)
        assert failed.value.failure == "too_large"


def test_a_file_of_too_many_blocks_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("artifactr.files.blender.document.BLOCKS", 100)
    with pytest.raises(AppFailed, match="more than 100 blocks"):
        scan(SOURCE)


def test_a_file_must_hold_one_catalogue() -> None:
    data = plain("primitives")
    blend = read(bytes(data))
    (dna,) = [block for block in blend.blocks if block.code == b"DNA1"]
    twice = ended(data, b"DNA1", 0, bytes(data[dna.bytes_start : dna.end]))
    with pytest.raises(AppFailed, match="one catalogue"):
        scan(twice)
    without = bytes(data[: dna.start] + data[dna.end :])
    with pytest.raises(AppFailed, match="one catalogue"):
        scan(without)


def test_a_data_block_outside_the_allowed_ones_is_refused() -> None:
    with pytest.raises(AppFailed, match=r"a data-block that isn't allowed: b'XX'"):
        scan(ended(plain("primitives"), b"XX\0\0", RAW, b""))
    with pytest.raises(AppFailed, match="a node group"):
        scan(ended(plain("primitives"), b"NT\0\0", RAW, b""))


def test_a_struct_outside_the_allowed_ones_is_refused() -> None:
    catalogue = read(SOURCE).catalogue
    for name, why in (("PackedFile", "a packed file"), ("Strip", "a struct that isn't allowed")):
        index = index_of(name)
        payload = bytes(catalogue.size(index))
        with pytest.raises(AppFailed, match=f"{why}: {name}"):
            scan(ended(plain("primitives"), b"DATA", index, payload))


def test_raw_data_is_allowed_but_a_script_nodes_name_in_it_isnt() -> None:
    assert scan(ended(plain("primitives"), b"DATA", RAW, b"any bytes at all"))
    with pytest.raises(AppFailed, match="a script node"):
        scan(ended(plain("primitives"), b"DATA", RAW, b"..ShaderNodeScript.."))


def test_a_pointer_at_a_struct_outside_the_allowed_ones_is_refused_with_why() -> None:
    with pytest.raises(AppFailed, match=r"Mesh\.key points at a struct that isn't allowed: Key"):
        scan(changed("primitives", pointed("Mesh", "key", "Object")))


def test_a_pointer_at_raw_data_as_a_struct_or_plain_data_at_a_struct_is_refused() -> None:
    def at_raw(data: bytearray) -> None:
        inserted(None, b"raw bytes", 0x10)(data)
        at = first(data, "Object")[1] + offset_of(data, "Object", "parent")
        struct.pack_into("<Q", data, at, 0x10)

    with pytest.raises(AppFailed, match=r"Object\.parent points at raw data, not Object"):
        scan(changed("primitives", at_raw))
    with pytest.raises(AppFailed, match=r"Mesh\.poly_offset_indices points at Object, not int"):
        scan(changed("primitives", pointed("Mesh", "poly_offset_indices", "Object")))
    with pytest.raises(AppFailed, match=r"Object\.runtime points at Object"):
        scan(changed("primitives", pointed("Object", "runtime", "Object")))


def test_a_data_block_pointer_where_blender_saves_none_is_refused() -> None:
    with pytest.raises(AppFailed, match=r"Object\.data points at no block, not ID|another type"):
        scan(changed("primitives", written("Object", "data", (0x99).to_bytes(8, "little"))))


def test_data_before_any_block_it_belongs_to_is_refused() -> None:
    data = plain("primitives")
    raw = HEAD.pack(b"DATA", RAW, 0x10, 0, 1)
    with pytest.raises(AppFailed, match="data before any block"):
        scan(bytes(data[: len(HEADER)] + raw + data[len(HEADER) :]))


def test_a_data_block_or_the_thumbnail_of_another_struct_than_its_code_is_refused() -> None:
    data = plain("primitives")
    blend = read(bytes(data))
    for code in (b"OB\0\0", b"TEST"):
        block = next(b for b in blend.blocks if b.code == code)
        changed_data = bytearray(data)
        values = list(HEAD.unpack_from(changed_data, block.start))
        values[1] = RAW if code != b"TEST" else index_of("Object")
        HEAD.pack_into(changed_data, block.start, *values)
        with pytest.raises(AppFailed, match=r"is raw data|block holds a Object"):
            scan(bytes(changed_data))


def test_a_scans_work_is_bounded() -> None:
    with pytest.raises(AppFailed, match="too long to scan") as failed:
        scan(SOURCE, work=100)
    assert failed.value.failure == "too_large"


def test_a_mesh_array_of_pointers_is_read_entry_by_entry() -> None:
    assert scan(CORPUS.source("materials")), "its material, a pointer at a material"


@pytest.mark.parametrize(
    ("frames", "kept"),
    [
        ("split", True),
        # zstandard reads no frame past a leading skippable one: refused, never misread.
        ("leading_skippable", False),
        ("skippable_only", False),
        ("dictionary", False),
        ("trailing_garbage", False),
    ],
)
def test_zstd_is_read_frame_by_frame_and_nothing_else(frames: str, kept: bool) -> None:
    data = bytes(plain("primitives"))
    compressor = zstandard.ZstdCompressor()
    skippable = (0x184D2A50).to_bytes(4, "little") + (4).to_bytes(4, "little") + b"skip"
    half = len(data) // 2
    content = {
        "split": compressor.compress(data[:half]) + compressor.compress(data[half:]),
        "leading_skippable": skippable + compressor.compress(data),
        "skippable_only": skippable,
        "dictionary": zstandard.ZstdCompressor(
            dict_data=zstandard.ZstdCompressionDict(b"BLENDER" * 64)
        ).compress(data),
        "trailing_garbage": compressor.compress(data) + b"\xff" * 16,
    }[frames]
    if kept:
        assert scan(content).content == scan(data).content
    else:
        with pytest.raises(AppFailed):
            scan(content)


def test_an_object_of_a_type_the_commands_dont_make_is_refused() -> None:
    def curve(data: bytearray) -> None:
        offset, _ = read(bytes(data)).catalogue.field(index_of("Object"), b"type")
        struct.pack_into("<h", data, first(data, "Object")[1] + offset, 2)

    with pytest.raises(AppFailed, match="an object of type 2, which isn't allowed"):
        scan(changed("primitives", curve))


def test_the_catalogue_is_read_as_blender_lays_its_structs_out() -> None:
    catalogue = read(SOURCE).catalogue
    for index in range(len(catalogue.structs)):
        assert sum(size for *_, size in catalogue.fields(index)) == catalogue.size(index)
    assert {"ID", "ModifierData", "SpaceLink"} <= catalogue.pointable
    assert catalogue.pointable >= STRUCTS
    assert catalogue.field(index_of("Object"), b"parent") == (496, 8)


def test_a_compressed_file_and_its_bytes_have_one_fingerprint() -> None:
    data = bytes(plain("primitives"))
    assert fingerprint(zstandard.ZstdCompressor().compress(data)) == fingerprint(data)
