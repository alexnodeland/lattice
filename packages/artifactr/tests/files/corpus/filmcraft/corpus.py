"""FilmCraft's corpus: a `.fcproj` per feature, made by FilmCraft, each feature read out of its
JSON; and the projects made to break it."""

import json
from functools import partial
from typing import Any

from artifactr.files.app import App
from artifactr.files.craft.project import LIMIT
from artifactr.files.filmcraft import Subprocess
from tests.files.corpus.filmcraft.features import read
from tests.files.corpus.filmcraft.make import HERE, MADE
from tests.files.corpus.harness import Corpus, dense


def kept(content: bytes) -> bytes:
    """FilmCraft stamps nothing on a save: two saves in a row are the same bytes."""
    return content


def held(feature: str) -> dict[str, Any]:
    """A feature's project, to break."""
    return json.loads(MADE.committed(feature))


def written(project: dict[str, Any]) -> bytes:
    return json.dumps(project).encode()


def not_json() -> bytes:
    """A project that says it is a `.fcproj`, and then isn't JSON."""
    return b'{"format": "filmcraft.project", nope'


def too_large() -> bytes:
    """A project larger than any that holds no media."""
    return b'{"format": "filmcraft.project", "pad": "' + b" " * LIMIT + b'"}'


def nested() -> bytes:
    """A project nested far deeper than any FilmCraft writes."""
    return b'{"format": "filmcraft.project", "project": ' + b"[" * 100_000 + b"]" * 100_000 + b"}"


def no_items() -> bytes:
    """A project whose items aren't a project's."""
    project = held("bins")
    project["project"]["items"] = ["Color Matte"]
    return written(project)


def media(path: str) -> bytes:
    """A project whose generated medium is a file's instead, at a path."""
    project = held("generated_media")
    project["project"]["items"]["1"]["kind"]["Media"]["media"] = {"File": {"path": path}}
    return written(project)


def proxy() -> bytes:
    """A project whose generated medium has a proxy, a file outside it."""
    project = held("generated_media")
    project["project"]["items"]["2"]["kind"]["Media"]["proxy"] = {"path": "/etc/hosts"}
    return written(project)


def look(lut: str) -> bytes:
    """A project whose colour effect reads a LUT that isn't one of FilmCraft's own."""
    project = held("color")
    clip = project["project"]["items"]["7"]["kind"]["Sequence"]["video_tracks"][0]["items"][0]
    clip["effects"][0]["params"]["look_lut"]["value"]["Text"] = lut
    return written(project)


def version(schema: int) -> bytes:
    """A project of another release's schema."""
    return written({**held("clips"), "schema_version": schema})


def huge_frame() -> bytes:
    """A sequence of 200,000 by 200,000 pixels: a frame of 160 GB."""
    project = held("clips")
    settings = project["project"]["items"]["7"]["kind"]["Sequence"]["settings"]
    settings.update(width=200_000, height=200_000)
    return written(project)


def adapter(cli: str, version: str) -> App:
    """FilmCraft's CLI confines nothing: its corpus is the only file it is given."""
    return Subprocess(cli, version=version, trusted=True)


CORPUS = Corpus(
    app="filmcraft",
    extension=".fcproj",
    folder=HERE,
    makers=MADE.makers(),
    read=read,
    kept=kept,
    adapter=adapter,
    hostile={
        "not_json": not_json,
        "too_large": too_large,
        "nested": nested,
        "dense": partial(
            dense, b'{"format": "filmcraft.project", "project": {"items": ', b"}}", LIMIT
        ),
        "no_items": no_items,
        "media_at_a_path": partial(media, "/etc/hosts"),
        "media_up_the_tree": partial(media, "../../../etc/hosts"),
        "proxy": proxy,
        "lut_at_a_path": partial(look, "/etc/hosts"),
        "lut_in_a_library": partial(look, "lib:1"),
        "future_version": partial(version, 99),
        "older_version": partial(version, 3),
        "huge_frame": huge_frame,
    },
)
"""FilmCraft 0.8.0 keeps every feature. A clip of an item the project doesn't hold, a sequence
of 10^18 ticks and 60,000 items are each opened, not refused, so none is a hostile file here;
the last takes FilmCraft seconds, well within a call's deadline."""
