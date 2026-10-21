"""SoundCraft's corpus: one `.scraft` per feature, beside this, each made by SoundCraft itself.

Each file is what SoundCraft's adapter saves of its feature's script, a batch of SoundCraft's own
commands on a blank session, of MIDI and its built-in instruments only. SoundCraft numbers what
a session holds in order from 1, so a script names a track or clip an earlier command made by
that number. A position is in samples, 48,000 a second. `python -m
tests.files.corpus.soundcraft.make CLI`, from `packages/artifactr`, writes them again.
"""

import asyncio
import sys
from pathlib import Path
from typing import Final

from artifactr.files.soundcraft import Subprocess
from tests.files.corpus.harness import pinned
from tests.files.corpus.made import Made, step

HERE: Final = Path(__file__).parent

KEYS: Final = step("track.new", kind="instrument", name="Keys")
"""An instrument track of the subtractive synth: 1."""

MADE: Final = Made(
    folder=HERE,
    extension=".scraft",
    scripts={
        "tracks": [
            KEYS,
            step("track.new", kind="instrument", name="Drums", instrument="drum_synth"),
            step("track.new", kind="aux", name="Room"),
        ],
        "midi": [
            KEYS,
            step("midi.new_clip", track=1, length=96_000),
            step("midi.note_add", clip=2, pitch=60, start_ticks=0, length_ticks=480),
            step("midi.note_add", clip=2, pitch=64, start_ticks=480, velocity=80),
        ],
        "instruments": [
            KEYS,
            step("track.new", kind="instrument", name="Kit", instrument="drum_synth"),
            step("track.new", kind="instrument", name="Pad", instrument="sampler"),
        ],
        "mixer": [
            KEYS,
            step("mix.volume", tracks=[1], db=-6),
            step("mix.pan", tracks=[1], pan=-0.5),
            step("mix.mute", tracks=[1]),
        ],
        "inserts": [
            KEYS,
            step("mix.insert", track=1, slot=0, plugin="compressor"),
            step("mix.insert", track=1, slot=1, plugin="plate_reverb"),
        ],
        "sends": [
            KEYS,
            step("mix.new_bus", name="Verb"),
            step("mix.send", track=1, slot=0, bus="Verb", level_db=-3),
        ],
        "automation": [
            KEYS,
            step("automation.set_point", track=1, param="volume", at=0, value=-12),
            step("automation.set_point", track=1, param="volume", at=48_000, value=0),
        ],
        "markers": [
            step("markers.add", name="Verse", at=48_000),
            step("markers.add", name="Chorus", at=96_000),
        ],
        "tempo_and_meter": [
            step("event.tempo", bpm=96),
            step("event.meter", numerator=3, denominator=4),
            step("event.add_key_change", key="D minor"),
        ],
        "comments": [KEYS, step("track.comments", track=1, comments="Play it softly")],
    },
)
"""Each feature SoundCraft's report compares, and the script that makes its file."""


def main() -> None:
    soundcraft = Subprocess(sys.argv[1], version=pinned("soundcraft"))
    asyncio.run(MADE.write(soundcraft))


if __name__ == "__main__":
    main()
