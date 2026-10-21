"""A project of tiny values at its size's limit, the most work to read, is read once a call."""

import pytest
from pydantic import JsonValue, TypeAdapter

from artifactr.files.app import AppFailed
from artifactr.files.craft import project
from artifactr.files.craft.project import LIMIT, whole
from artifactr.files.effectcraft import media_type as ecproj
from artifactr.files.effectcraft import outside as footage
from artifactr.files.filmcraft import media_type as fcproj
from artifactr.files.filmcraft import outside as media
from artifactr.files.soundcraft import media_type as scraft
from artifactr.files.soundcraft import outside as sources
from tests.files.corpus.corpora import CORPORA

READS = {
    "filmcraft": (".fcproj", fcproj, media),
    "effectcraft": (".ecproj", ecproj, footage),
    "soundcraft": (".scraft", scraft, sources),
}


class _Counted:
    """pydantic's JSON reader, counting the projects it reads."""

    def __init__(self) -> None:
        self.reads = 0
        self._json: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)

    def validate_json(self, data: bytes) -> JsonValue:
        self.reads += 1
        return self._json.validate_json(data)


@pytest.mark.parametrize("app", sorted(READS))
def test_a_dense_project_is_parsed_once_however_often_it_is_asked_of(
    app: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its format and what it draws from outside are read from one parse: the work is bounded by
    `LIMIT` bytes, read once, whatever the machine's clock."""
    content = CORPORA[app].hostile_file("dense")
    assert LIMIT - 2 <= len(content) <= LIMIT
    extension, media_type, outside = READS[app]
    counted = _Counted()
    monkeypatch.setattr(project, "_JSON", counted)
    project._parsed.cache_clear()
    failure = None
    try:
        whole(content, extension, media_type, outside)
    except AppFailed as refused:
        failure = refused.failure
    assert counted.reads == 1
    assert failure in {None, "refused"}, "refused as no project, or left for its app to refuse"
