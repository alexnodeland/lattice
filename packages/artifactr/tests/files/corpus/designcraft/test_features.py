"""DesignCraft's corpus: what each feature's value means."""

import io
import zipfile

from tests.files.corpus.designcraft.corpus import CORPUS
from tests.files.corpus.designcraft.features import READERS, Value, read


def value(feature: str) -> Value:
    return read(feature, CORPUS.source(feature))


def test_a_features_value_is_what_it_means() -> None:
    assert value("paragraph_styles") == [
        ("Heading", "24", "CenterAlign", "Contract"),
        ("$ID/NormalParagraphStyle", "12", None, "Pay within thirty days."),
    ]
    assert value("character_styles")[1] == ("Emphasis", "Italic", "within thirty days")
    assert value("threaded_frames") == [
        ("Flowing Flowing Flow", ((36.0, -360.0, 290.0, -276.0), (322.0, -360.0, 576.0, -276.0)))
    ]
    assert value("colors") == [("Brand", "RGB", (200.0, 30.0, 60.0), "Coloured")]
    assert [words for _, words in value("pages")] == [("Page 1",), ("Page 2",), ("Page 3",)]


def test_every_feature_has_a_reader() -> None:
    assert set(READERS) == set(CORPUS.makers)


def test_each_hostile_file_is_its_format_broken() -> None:
    def names(name: str) -> list[str]:
        with zipfile.ZipFile(io.BytesIO(CORPUS.hostile_file(name))) as archive:
            return archive.namelist()

    with zipfile.ZipFile(io.BytesIO(CORPUS.hostile_file("bomb"))) as archive:
        (story,) = (i for i in archive.infolist() if i.filename.startswith("Stories/"))
        assert story.file_size == 300 << 20
    with zipfile.ZipFile(io.BytesIO(CORPUS.hostile_file("unparsed"))) as archive:
        assert archive.read("designmap.xml") == b"<Document"
    assert not [name for name in names("spreadless") if name.startswith("Spreads/")]
