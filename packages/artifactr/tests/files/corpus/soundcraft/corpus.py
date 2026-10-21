"""SoundCraft's corpus: a `.scraft` per feature, made by SoundCraft, each feature read out of its
JSON; and the sessions made to break it."""

import json
from functools import partial
from typing import Any

from artifactr.files.app import App
from artifactr.files.craft.project import LIMIT
from artifactr.files.soundcraft import Subprocess
from tests.files.corpus.harness import Corpus, dense
from tests.files.corpus.soundcraft.features import read
from tests.files.corpus.soundcraft.make import HERE, MADE

SAID = b'{"format_version": 1, "tracks": []'
"""How a `.scraft` starts, saying its version."""


def kept(content: bytes) -> bytes:
    """SoundCraft stamps nothing on a save: two saves in a row are the same bytes."""
    return content


def held(feature: str) -> dict[str, Any]:
    """A feature's session, to break."""
    return json.loads(MADE.committed(feature))


def written(session: dict[str, Any]) -> bytes:
    return json.dumps(session).encode()


def not_json() -> bytes:
    """A session that says its version, and then isn't JSON."""
    return SAID + b", nope"


def too_large() -> bytes:
    """A session larger than any that holds no audio."""
    return SAID + b', "pad": "' + b" " * LIMIT + b'"}'


def nested() -> bytes:
    """A session nested far deeper than any SoundCraft writes."""
    return SAID + b', "busses": ' + b"[" * 100_000 + b"]" * 100_000 + b"}"


def no_sources() -> bytes:
    """A session whose sources aren't a session's."""
    return written({**held("midi"), "sources": "take.wav"})


def audio(path: str) -> bytes:
    """A session holding a take, a file at a path."""
    source = {"id": 9, "name": "take", "path": path, "channels": 2, "frames": 48_000}
    return written({**held("midi"), "sources": [{**source, "sample_rate": 48_000}]})


def video() -> bytes:
    """A session holding a video, a file outside it."""
    return written({**held("midi"), "videos": [{"name": "picture", "path": "picture.mov"}]})


def plugin(at: str, named: str) -> bytes:
    """A session whose instrument, or first insert, is another maker's plugin."""
    session = held("inserts")
    track = session["tracks"][0]
    if at == "instrument":
        track["instrument"]["plugin"] = named
    else:
        track["mixer"]["inserts"][0]["plugin"] = named
    return written(session)


def future_version() -> bytes:
    """A session of a version SoundCraft doesn't know yet."""
    return written({**held("midi"), "format_version": 99})


def unread_clip() -> bytes:
    """A clip of audio that names no place in its source."""
    session = held("midi")
    session["tracks"][0]["playlists"][0]["clips"][0]["content"] = {"Audio": {"source": 7}}
    return written(session)


def adapter(cli: str, version: str) -> App:
    """SoundCraft's CLI is confined to the call's read and write roots."""
    return Subprocess(cli, version=version)


CORPUS = Corpus(
    app="soundcraft",
    extension=".scraft",
    folder=HERE,
    makers=MADE.makers(),
    read=read,
    kept=kept,
    adapter=adapter,
    hostile={
        "not_json": not_json,
        "too_large": too_large,
        "nested": nested,
        "dense": partial(dense, b'{"format_version": 1, "sources": [], "tracks": ', b"}", LIMIT),
        "no_sources": no_sources,
        "audio_at_a_path": partial(audio, "/etc/hosts"),
        "audio_up_the_tree": partial(audio, "../../../etc/hosts"),
        "video": video,
        "vst3_instrument": partial(plugin, "instrument", "vst3:0123456789ABCDEF"),
        "clap_insert": partial(plugin, "insert", "clap:com.example.reverb"),
        "audio_unit_insert": partial(plugin, "insert", "au:aufx:dely:appl"),
        "future_version": future_version,
        "unread_clip": unread_clip,
    },
)
"""SoundCraft 0.8.0 keeps every feature. A session of a sample rate of a billion or of none,
an older version, a sampler naming a sample it doesn't hold, 150,000 notes and 2,000 tracks are
each opened, not refused, so none is a hostile file here; the notes take SoundCraft a second."""
