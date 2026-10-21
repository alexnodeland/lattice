"""FilmCraft's corpus: one `.fcproj` per feature, beside this, each made by FilmCraft itself.

Each file is what FilmCraft's adapter saves of its feature's script, a batch of FilmCraft's own
commands on a blank project, at a small frame size, its media its own generators'. FilmCraft
numbers what a project holds in order from 1, the first sequence taking 7 after its six tracks,
so a script names what an earlier command made by that number. `python -m
tests.files.corpus.filmcraft.make CLI`, from `packages/artifactr`, writes them again.
"""

import asyncio
import sys
from pathlib import Path
from typing import Final

from artifactr.files.filmcraft import Subprocess
from tests.files.corpus.harness import pinned
from tests.files.corpus.made import Made, step

HERE: Final = Path(__file__).parent

SEQUENCE: Final = step("file.newSequence", name="Main", width=64, height=36, fps=24)
"""A sequence of 64 by 36 at 24 frames a second: 7, its tracks 1 to 6."""

MATTE: Final = step("file.newColorMatte", color="#d04020", seconds=2)
"""A red matte two seconds long, after the sequence: 8."""

PLACED: Final = step("timeline.place", item=8, track="V1", seconds=0, insert=False)
"""The matte placed at the start of the first video track: its clip, 9."""

MADE: Final = Made(
    folder=HERE,
    extension=".fcproj",
    scripts={
        "sequences": [
            SEQUENCE,
            step("file.newSequence", name="Square", width=48, height=48, fps=30),
        ],
        "bins": [
            step("file.newBin", name="Selects"),
            step("file.newBin", name="Inner", parent=1),
            step("file.newColorMatte", color="#2060d0", seconds=1),
            step("project.moveToBin", items=[3], bin=2),
        ],
        "generated_media": [
            step("file.newColorMatte", color="#20a040", seconds=1),
            step("file.newBarsAndTone", seconds=1),
            step("file.newBlackVideo", seconds=1),
            step("file.importDemoFootage", scene="Plasma"),
        ],
        "clips": [
            SEQUENCE,
            MATTE,
            step("file.newColorMatte", color="#2040d0", seconds=2),
            PLACED,
            step("timeline.place", item=9, track="V1", seconds=2, insert=False),
        ],
        "transitions": [
            SEQUENCE,
            MATTE,
            step("file.newColorMatte", color="#2040d0", seconds=2),
            PLACED,
            step("timeline.place", item=9, track="V1", seconds=2, insert=False),
            step("sequence.applyVideoTransition", clip=10, effect="cross_dissolve", edge="out"),
        ],
        "effects": [
            SEQUENCE,
            MATTE,
            PLACED,
            step("effects.apply", clips=[9], effect="gaussian_blur"),
            step("effects.setParam", clip=9, effect="gaussian_blur", param="blurriness", value=12),
        ],
        "keyframes": [
            SEQUENCE,
            MATTE,
            PLACED,
            step(
                "effects.setParam",
                clip=9,
                effect="opacity",
                param="opacity",
                value=0,
                time=0,
                keyframe=True,
            ),
            step(
                "effects.setParam",
                clip=9,
                effect=1,
                param="opacity",
                value=100,
                time=254_016_000_000,
                keyframe=True,
            ),
        ],
        "titles": [
            SEQUENCE,
            step("graphics.newText", text="Hello", seconds=2),
            step("graphics.set", clip=9, layer=0, props={"size": 24, "fill_color": "#ffcc00"}),
        ],
        "shapes": [
            SEQUENCE,
            step("graphics.newShape", shape="ellipse", size=[20, 10], seconds=2),
        ],
        "captions": [
            SEQUENCE,
            step("captions.newTrack", format="Subtitle"),
            step("captions.add", text="First words", seconds=0, durationSeconds=1),
            step("captions.add", text="Second words", seconds=1, durationSeconds=1),
        ],
        "markers": [
            SEQUENCE,
            step("markers.add", name="Beat", comment="Cut here", time=254_016_000_000),
            step("markers.addChapter", name="Part two", time=508_032_000_000),
        ],
        "audio": [
            SEQUENCE,
            step("file.newBarsAndTone", seconds=2),
            step("timeline.place", item=8, track="V1", audioTrack="A1", seconds=0, insert=False),
        ],
        "color": [
            SEQUENCE,
            MATTE,
            PLACED,
            step("effects.apply", clips=[9], effect="lumetri"),
            step("lumetri.setLook", clip=9, lut="builtin:look-teal-orange"),
        ],
    },
)
"""Each feature FilmCraft's report compares, and the script that makes its file."""


def main() -> None:
    filmcraft = Subprocess(sys.argv[1], version=pinned("filmcraft"), trusted=True)
    asyncio.run(MADE.write(filmcraft))


if __name__ == "__main__":
    main()
