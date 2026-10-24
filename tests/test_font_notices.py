"""The typefaces' notices agree with each other, and name the Liberation Sans that ships."""

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
WORKER = ROOT / "packages/stackr/workers/diagrams/FONTS.txt"
PORTALR = ROOT / "packages/portalr/web/ui/licenses/excalidraw-faces.txt"
LIBERATION = ROOT / "packages/portalr/web/ui/fonts/LiberationSans-Regular.woff2"
SEPARATOR = "=" * 80 + "\n"


def sections(path: Path) -> dict[str, str]:
    """A notice file's sections, each by its heading, as the separators divide the file."""
    found: dict[str, str] = {}
    for part in path.read_text().split(SEPARATOR)[1:]:
        heading, _, body = part.partition("\n")
        found[heading.removeprefix("## ")] = body
    return found


def test_the_faces_both_files_carry_have_one_notice() -> None:
    worker, portalr = sections(WORKER), sections(PORTALR)
    shared = sorted(worker.keys() & portalr.keys())
    assert shared == sorted(
        [
            "Assistant",
            "Cascadia Code",
            "Comic Shanns",
            "Excalifont",
            "Liberation Sans",
            "Lilita One",
            "Nunito",
            "Virgil",
            "Web fonts, embedding and Reserved Font Names: the OFL-FAQ, as read here",
            "Xiaolai: not carried until its author answers (lattice#679)",
        ]
    )
    assert [name for name in shared if worker[name] != portalr[name]] == []


def test_the_notice_names_the_liberation_sans_that_ships() -> None:
    sha = hashlib.sha256(LIBERATION.read_bytes()).hexdigest()
    for path in (WORKER, PORTALR):
        notice = sections(path)["Liberation Sans"]
        assert sha in re.sub(r"\s+", "", notice), path
        assert "fontTools 4.62.1 and brotli 1.2.1" in notice
