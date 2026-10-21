"""A project of tiny values at its size's limit, the most work to read, is refused in time."""

import time

import pytest

from artifactr.files.app import AppFailed
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


@pytest.mark.parametrize("app", sorted(READS))
def test_a_dense_project_is_read_once_and_quickly(app: str) -> None:
    content = CORPORA[app].hostile_file("dense")
    assert LIMIT - 2 <= len(content) <= LIMIT
    extension, media_type, outside = READS[app]
    failure = None
    started = time.monotonic()
    try:
        whole(content, extension, media_type, outside)
    except AppFailed as refused:
        failure = refused.failure
    assert time.monotonic() - started < 2, "read in a second or so, under any deadline"
    assert failure in {None, "refused"}, "refused as no project, or left for its app to refuse"
