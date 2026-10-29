"""A stand-in for `blender` running the adapter's script: its steps, as far as the adapter sees.

It saves the source it is given as it was, or the corpus' primitives for a blank file, and reads
an object for each `cube` command after the corpus' cube; any other command is refused, but
`unsaved`, after which nothing is saved. A page narrower than 32 pixels isn't drawn; a file
whose scene is named `Empty` is refused as the script refuses an empty scene, and one named
`NoCamera` as a scene with no camera. Run as
`python -I fake_cli.py --background ... --python script.py -- --pass CALL`.
"""

import json
import shutil
import sys
from pathlib import Path

PNG = b"\x89PNG\r\n\x1a\n"
PRIMITIVES = Path(__file__).parents[1] / "corpus" / "blender" / "primitives.blend"


def main() -> None:
    assert sys.argv[sys.argv.index("--python") + 2] == "--", "the script's arguments are its own"
    called = Path(sys.argv[sys.argv.index("--pass") + 1])
    here = called.parent
    call = json.loads(called.read_text())
    result: dict[str, object] = {"version": "5.2.2"}
    try:
        result["result"] = step(here, call)
    except ValueError as refused:
        result["refused"] = str(refused)
    (here / "result.json").write_text(json.dumps(result))


def step(here: Path, call: dict) -> dict:
    if call["step"] == "render":
        source = (here / "in" / "document.blend").read_bytes()
        if b"SCEmpty\0" in source:
            raise ValueError("nothing to draw: the scene is empty")
        if b"SCNoCamera\0" in source:
            raise ValueError("nothing to draw: the scene has no camera")
        if call["width"] >= 32:
            (here / "out" / "page.png").write_bytes(PNG)
        return {}
    objects = [{"name": "Cube", "type": "MESH", "collections": ["Scene Collection"]}]
    names = [command["name"] for command in call.get("commands", [])]
    for index, name in enumerate(names):
        if name not in {"cube", "unsaved"}:
            raise ValueError(f"command {index + 1}: no command {name!r}")
        objects.append({"name": f"Cube{index}", "type": "MESH", "collections": ["Props"]})
    if call["step"] == "apply" and "unsaved" not in names:
        source = here / "in" / "document.blend"
        shutil.copy(source if source.exists() else PRIMITIVES, here / "out" / "document.blend")
    return {"objects": objects, "materials": ["Red"], "collections": ["Props"]}


main()
