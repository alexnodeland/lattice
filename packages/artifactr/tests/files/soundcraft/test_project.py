"""Whether bytes are a `.scraft`, told from its JSON, and what one draws from outside it."""

import json

import pytest

from artifactr.files.app import AppFailed
from artifactr.files.manifest import SCRAFT
from artifactr.files.soundcraft import media_type, outside


def scraft(**fields: object) -> bytes:
    return json.dumps({"format_version": 1, "tracks": [], **fields}).encode()


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (scraft(), SCRAFT),
        (b'{"tracks": [{"name": "Keys"}], "format_version": 2}', SCRAFT),
        (b'{"format_version": "1", "tracks": []}', None),
        (b'{"format_version": 1, "tracks": {}}', None),
        (b'{"tracks": []}', None),
        (b"[1]", None),
        (b"", None),
    ],
)
def test_a_scraft_is_told_by_its_version_and_its_tracks(
    content: bytes, expected: str | None
) -> None:
    assert media_type(content) == expected


def test_midi_and_soundcrafts_own_plugins_draw_nothing_from_outside() -> None:
    keys = {"name": "Keys", "instrument": {"plugin": "subtractive_synth"}, "comments": "au"}
    inserts = [{"plugin": "compressor"}, None]
    assert outside(scraft(tracks=[{**keys, "mixer": {"inserts": inserts}}], sources=[])) == []


def test_audio_video_and_other_makers_plugins_are_drawn_from_outside() -> None:
    tracks = [
        {"instrument": {"plugin": "vst3:0123"}, "mixer": {"inserts": [{"plugin": "au:x"}]}},
        {"instrument": {"plugin": "vst3:0123"}, "mixer": {"inserts": [{"plugin": "clap:y"}]}},
    ]
    session = scraft(tracks=tracks, sources=[{"name": "take"}], videos=[{"name": "picture"}])
    assert outside(session) == ["take", "picture", "au:x", "clap:y", "vst3:0123"]


def test_a_session_whose_sources_arent_a_sessions_is_refused() -> None:
    with pytest.raises(AppFailed, match="its sources aren't a session's") as refused:
        outside(scraft(sources=[["take.wav"]]))
    assert refused.value.failure == "refused"
