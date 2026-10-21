"""EffectCraft's corpus: one `.ecproj` per feature, beside this, each made by EffectCraft itself.

Each file is what EffectCraft's adapter saves of its feature's script, a batch of EffectCraft's
own commands on a blank project, in a small composition. A script names a layer by its name,
and an item of the project by its name too. `python -m tests.files.corpus.effectcraft.make CLI`,
from `packages/artifactr`, writes them again.
"""

import asyncio
import sys
from pathlib import Path
from typing import Final

from artifactr.files.effectcraft import Subprocess
from tests.files.corpus.harness import pinned
from tests.files.corpus.made import Made, step

HERE: Final = Path(__file__).parent

COMP: Final = step("comp.new", name="Main", width=64, height=36, frameRate=24, duration=2)
"""A composition of 64 by 36 at 24 frames a second, two seconds long."""

SOLID: Final = step("layer.newSolid", name="Red", color="#d04020")
"""A red solid in the composition."""

MADE: Final = Made(
    folder=HERE,
    extension=".ecproj",
    scripts={
        "compositions": [
            COMP,
            step("comp.new", name="Square", width=48, height=48, frameRate=30, duration=1),
        ],
        "folders": [
            COMP,
            step("project.newFolder", name="Parts"),
            step("project.newFolder", name="Inner"),
            step("project.move", items=["Inner"], folder="Parts"),
            step("project.move", items=["Main"], folder="Inner"),
        ],
        "solids": [COMP, SOLID, step("layer.newSolid", name="Blue", color="#2040d0")],
        "text": [
            COMP,
            step("layer.newText", text="Hello", size=24),
            step("layer.newText", text="Second line", name="Body", size=12),
        ],
        "shapes": [
            COMP,
            step("layer.newShape", kind="ellipse", name="Dot", size=[20, 10], fill="#20a040"),
            step("layer.newShape", kind="star", name="Star", size=[16, 16]),
        ],
        "keyframes": [
            COMP,
            SOLID,
            step("prop.addKey", layer="Red", path="transform/position", time=0, value=[0, 0]),
            step("prop.addKey", layer="Red", path="transform/position", time=1, value=[32, 18]),
        ],
        "effects": [
            COMP,
            SOLID,
            step("effect.apply", effect="Gaussian Blur", layers=["Red"]),
        ],
        "masks": [COMP, SOLID, step("layer.addMask", layer="Red", shape="ellipse")],
        "expressions": [
            COMP,
            SOLID,
            step(
                "prop.setExpression",
                layer="Red",
                path="transform/rotation",
                expression="time * 90",
            ),
        ],
        "markers": [
            COMP,
            step("comp.addMarker", time=0.5, comment="Beat"),
            step("comp.addMarker", time=1.5, comment="Cut here"),
        ],
        "parenting": [
            COMP,
            SOLID,
            step("layer.newNull", name="Rig"),
            step("layer.setParent", layers=["Red"], parent="Rig"),
        ],
        "blend_modes": [
            COMP,
            SOLID,
            step("layer.setBlendMode", layers=["Red"], mode="Multiply"),
        ],
        "precomps": [
            COMP,
            SOLID,
            step("layer.precompose", layers=["Red"], name="Inside", mode="move"),
        ],
    },
)
"""Each feature EffectCraft's report compares, and the script that makes its file."""


def main() -> None:
    effectcraft = Subprocess(sys.argv[1], version=pinned("effectcraft"))
    asyncio.run(MADE.write(effectcraft))


if __name__ == "__main__":
    main()
