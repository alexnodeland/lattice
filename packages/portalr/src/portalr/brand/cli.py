"""``portalr brand``: start a kit, and check one, as the portal will (lattice RFC-0007).

Exit status: 0 when done, 1 when the kit has faults or the folder can't be written or read, and
2 when the command line isn't one ``portalr`` takes.
"""

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from portalr.brand.kit import load
from portalr.brand.tokens import DEFAULT, BrandError

HERE = Path(__file__).parent
STARTS = {
    "template": HERE / "template",
    "nightshade": HERE / "examples" / "nightshade",
    "calm": HERE / "examples" / "calm",
}
"""What `init --from` copies: a plain kit to fill in, or one of the two examples."""

CARRIES = """\
What it carries: brand.json (the product's names and words), tokens.light.json and
tokens.dark.json (the tokens it changes over portalr's default kit), and its marks under
assets/. tokens.reference.json is portalr's default kit in full, for looking tokens up; the
portal doesn't read it.
"""

TERMS = {
    "template": """\
Its names, words and marks are placeholders: replace them with the product's own, which are
yours. Any faces you add are under their own licences, which brand.json names and the kit
carries.
""",
    "example": """\
It is a copy of portalr's example kit, {start}: its name, words, marks and favicon are the
example's, under the MIT licence in its LICENSE.txt, and are no one's trademark. Replace them
with the product's own before serving it as yours.
""",
}


def notice(start: str) -> str:
    """The NOTICE a kit started from `start` carries: what it holds, and under what terms."""
    terms = TERMS["template" if start == "template" else "example"].format(start=start)
    return f"This brand kit was started by `portalr brand init` from {start}.\n\n{CARRIES}\n{terms}"


def shown(text: str) -> str:
    """Text for a terminal or a CI log, one line to each line: anything unprintable escaped."""
    return "\n".join(
        "".join(c if c.isprintable() else ascii(c)[1:-1] for c in line) for line in text.split("\n")
    )


def init(folder: Path, start: str) -> str:
    """Start a kit in `folder`, which is new or empty, from `start`; what was done, in words.

    The kit is written in a folder beside it and moved into place whole, so a failure leaves no
    half a kit; a process killed while it writes leaves that folder, `.<name>.*`, to remove.

    Raises:
        BrandError: If `folder` is anything but a new or empty folder.
        OSError: If it can't be written.
    """
    if folder.is_symlink() or (folder.exists() and (not folder.is_dir() or any(folder.iterdir()))):
        raise BrandError(f"{str(folder)!r}: not an empty folder; a kit starts in a new one")
    if not folder.parent.is_dir():
        raise BrandError(f"{str(folder.parent)!r}: no such folder to start a kit in")
    with tempfile.TemporaryDirectory(dir=folder.parent, prefix=f".{folder.name}.") as scratch:
        kit = Path(scratch) / "kit"
        shutil.copytree(STARTS[start], kit)
        reference = {
            "light": json.loads((DEFAULT / "tokens.light.json").read_text(encoding="utf-8")),
            "dark": json.loads((DEFAULT / "tokens.dark.json").read_text(encoding="utf-8")),
        }
        (kit / "tokens.reference.json").write_text(
            json.dumps(reference, indent=2) + "\n", encoding="utf-8"
        )
        (kit / "NOTICE").write_text(notice(start), encoding="utf-8")
        if folder.exists():
            folder.rmdir()
        kit.rename(folder)
    return (
        f"a kit started in {folder}, from {start}: check it with `portalr brand validate {folder}`"
    )


def validate(folder: Path, *, as_json: bool) -> tuple[str, bool]:
    """Check the kit in `folder` as the portal will: what it is, or its faults, and if it passed.

    Raises:
        BrandError: With every fault, one to a line, unless they are said `as_json`.
    """
    try:
        kit = load(folder)
    except BrandError as error:
        if not as_json:
            raise
        return json.dumps({"ok": False, "faults": str(error).split("\n")}), False
    if as_json:
        said: dict[str, object] = {
            "ok": True,
            "name": kit.brand.name,
            "hash": kit.hash,
            "faults": [],
        }
        return json.dumps(said), True
    return (
        f"{folder}: the kit {kit.brand.name!r} is one the portal can serve (hash {kit.hash})",
        True,
    )


def main(argv: list[str] | None = None) -> int:
    """``portalr``'s command line; its exit status."""
    parser = argparse.ArgumentParser(
        prog="portalr", epilog="exit status: 0 done, 1 faults, 2 usage"
    )
    commands = parser.add_subparsers(dest="group", required=True)
    brand = commands.add_parser("brand", help="brand kits (lattice RFC-0007)")
    kits = brand.add_subparsers(dest="command", required=True)
    started = kits.add_parser("init", help="start a kit in a new folder")
    started.add_argument("folder", type=Path)
    started.add_argument("--from", dest="start", choices=sorted(STARTS), default="template")
    checked = kits.add_parser("validate", help="check a kit, and say every fault")
    checked.add_argument("folder", type=Path)
    checked.add_argument(
        "--json", action="store_true", help="say it as one JSON object: ok, name, hash, faults"
    )
    said = parser.parse_args(argv)
    as_json = said.command == "validate" and said.json
    try:
        if said.command == "init":
            done, ok = init(said.folder, said.start), True
        else:
            done, ok = validate(said.folder, as_json=as_json)
    except (BrandError, OSError) as error:
        why = str(error) if isinstance(error, BrandError) else _failed(error)
        if as_json:
            sys.stdout.write(json.dumps({"ok": False, "faults": why.split("\n")}) + "\n")
        else:
            sys.stderr.write(shown(why) + "\n")
        return 1
    sys.stdout.write(shown(done) + "\n")
    return 0 if ok else 1


def _failed(error: OSError) -> str:
    """An operating system's refusal, in words: the file it names, where it names one."""
    why = error.strerror or str(error)
    return f"{error.filename}: {why}" if error.filename is not None else why
