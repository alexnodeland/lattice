# /// script
# dependencies = ["fonttools==4.62.1", "brotli==1.2.1"]
# ///
# fontTools isn't one of the project's dependencies: this script's own, above, and untyped here.
# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false
"""Fail unless the committed Liberation Sans 2.1.5 is what its notice says it is (lattice#679).

It downloads the release tarball at the tag liberation-fonts-ttf-2.1.5 names, checks its SHA-256 and
the TTF's, converts the TTF to WOFF2 as web/ui/licenses/excalidraw-faces.txt says (fontTools and
brotli, at the versions it names, with nothing else changed), and compares the result with
web/ui/fonts/LiberationSans-Regular.woff2. It needs the network, so it is not part of `check`.

Usage: scripts/check_liberation.py   (from portalr's directory)
"""

import hashlib
import io
import sys
import tarfile
import urllib.request
from pathlib import Path

from fontTools.ttLib import TTFont

URL = (
    "https://github.com/liberationfonts/liberation-fonts/files/7261482/"
    "liberation-fonts-ttf-2.1.5.tar.gz"
)
TARBALL = "7191c669bf38899f73a2094ed00f7b800553364f90e2637010a69c0e268f25d0"
TTF = "76d04c18ea243f426b7de1f3ad208e927008f961dc5945e5aad352d0dfde8ee8"
MEMBER = "liberation-fonts-ttf-2.1.5/LiberationSans-Regular.ttf"
COMMITTED = Path(__file__).parent.parent / "web" / "ui" / "fonts" / "LiberationSans-Regular.woff2"


def sha256(data: bytes) -> str:
    """The SHA-256 of some bytes, in hex."""
    return hashlib.sha256(data).hexdigest()


def problems() -> list[str]:
    """What differs from the notice: the tarball, the TTF, or the WOFF2 made from it."""
    with urllib.request.urlopen(URL, timeout=60) as response:
        tarball = response.read()
    if sha256(tarball) != TARBALL:
        return [f"the release tarball's SHA-256 is {sha256(tarball)}, not {TARBALL}"]
    with tarfile.open(fileobj=io.BytesIO(tarball)) as archive:
        member = archive.extractfile(MEMBER)
        assert member is not None
        ttf = member.read()
    if sha256(ttf) != TTF:
        return [f"the TTF's SHA-256 is {sha256(ttf)}, not {TTF}"]
    font = TTFont(io.BytesIO(ttf), recalcTimestamp=False)
    font.flavor = "woff2"
    converted = io.BytesIO()
    font.save(converted)
    if converted.getvalue() != COMMITTED.read_bytes():
        return [f"{COMMITTED.name} is not the TTF converted: {sha256(converted.getvalue())}"]
    return []


if __name__ == "__main__":
    found = problems()
    sys.stderr.write("".join(f"check_liberation: {problem}\n" for problem in found))
    sys.exit(1 if found else 0)
