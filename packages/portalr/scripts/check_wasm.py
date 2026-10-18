r"""Fail on a WebAssembly module in a built UI that web/wasm-allowlist.json doesn't list.

Both UIs' policy allows ``'wasm-unsafe-eval'``, for the modules their own build ships and no
others (portalr ADR-0041). This check finds every module in each UI's build, as Vite wrote it:

- a ``.wasm`` file;
- a module inlined in any other file as base64, by the encoding of its magic ``\0asm``,
  ``AGFzbQ``; the run is decoded to the module's bytes.

Raw magic outside a ``.wasm`` file can't be delimited, so it is a problem of its own. Each module
is known by the SHA-256 of its bytes, since Vite's file names change with every build. The
allow-list names, for each UI, each module's package and its digest. A module not listed, a listed
one the build doesn't hold, and raw magic each fail the check. Add a module or change its digest
only in a reviewed change that says why, as a size budget is raised (ADR-0040).

Usage: scripts/check_wasm.py   (from portalr's directory, after app's and admin's builds)
"""

import base64
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
STATIC = ROOT / "src" / "portalr" / "static"
ALLOWLIST = ROOT / "web" / "wasm-allowlist.json"
UIS = ("app", "admin")
MAGIC = b"\0asm"
INLINED = re.compile(rb"AGFzbQ[A-Za-z0-9+/]*={0,2}")
"""A module inlined as base64: its magic's encoding, and the rest of the run."""

type Found = dict[str, str]
"""Each module a build holds, by the SHA-256 of its bytes, and the file that holds it."""


def digest(module: bytes) -> str:
    """A module's SHA-256, in hex."""
    return hashlib.sha256(module).hexdigest()


def modules(ui: str, static: Path | None = None) -> tuple[Found, list[str]]:
    """The modules a built UI holds, and each file with magic that can't be delimited."""
    root = (static or STATIC) / ui
    if not (root / "index.html").is_file():
        raise SystemExit(f"check_wasm: {ui} isn't built: {root / 'index.html'} is missing")
    found: Found = {}
    raw: list[str] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        name = path.relative_to(root).as_posix()
        data = path.read_bytes()
        if path.suffix == ".wasm":
            found[digest(data)] = name
            continue
        for run in INLINED.findall(data):
            # Padding added to a run that has its own is ignored, so a run that lost its is whole.
            found[digest(base64.b64decode(run + b"=="))] = name
        if MAGIC in data:
            raw.append(name)
    return found, raw


def problems(ui: str, found: Found, raw: list[str], listed: list[dict[str, Any]]) -> list[str]:
    """Each module not listed, each listed one not built, and each file with raw magic."""
    allowed = {entry["sha256"]: entry["package"] for entry in listed}
    return [
        *(
            f"{ui}'s {name} holds a WebAssembly module (sha256 {sha}) that "
            "web/wasm-allowlist.json doesn't list"
            for sha, name in found.items()
            if sha not in allowed
        ),
        *(
            f"web/wasm-allowlist.json lists {package}'s module (sha256 {sha}) for {ui}, "
            f"which {ui}'s build doesn't hold"
            for sha, package in allowed.items()
            if sha not in found
        ),
        *(
            f"{ui}'s {name} holds WebAssembly's magic outside a .wasm file, not as base64"
            for name in raw
        ),
    ]


def main() -> int:
    """Print each UI's modules; return 1 on a module not listed, one listed but absent, or raw."""
    allowlist = json.loads(ALLOWLIST.read_text())
    if absent := [ui for ui in UIS if ui not in allowlist]:
        raise SystemExit(f"check_wasm: wasm-allowlist.json has no list for {', '.join(absent)}")
    failed: list[str] = []
    for ui in UIS:
        found, raw = modules(ui)
        sys.stdout.write(f"check_wasm: {ui}: {len(found)} WebAssembly module(s)\n")
        failed += problems(ui, found, raw, allowlist[ui])
    sys.stderr.write("".join(f"check_wasm: {problem}\n" for problem in failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
