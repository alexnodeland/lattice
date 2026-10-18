"""The fidelity harness: a crafting app's corpus, and what its report compares.

A [`Corpus`][tests.files.corpus.harness.Corpus] is one app's: one generated file per feature,
in its folder, how each feature's value is read out of a file, and what two saves in a row must
agree on. `test_fidelity.py` opens and saves each file in the app's pinned CLI, Nightly runs it
for each app with a corpus, and `conftest.py` writes the matrix (lattice RFC-0003, phase 2;
native files ADR-0009).
"""

import random
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from artifactr.files.app import App

PINS: Final = Path(__file__).parents[5] / "scripts" / "crafts"

GIVEN: Final = ("empty", "noise", "truncated")
"""The hostile files every app is given: nothing, noise, and a corpus file cut in half."""


@dataclass(frozen=True)
class Corpus:
    """One crafting app's corpus, and how its report reads it."""

    app: str
    """The app, by its name in `CRAFTS`."""

    extension: str
    """Its files' extension, such as `.docx`."""

    folder: Path
    makers: Mapping[str, Callable[[], bytes]]
    """Each feature, and what makes its file."""

    read: Callable[[str, bytes], object]
    """A feature's value in a file, which a save must keep."""

    kept: Callable[[bytes], object]
    """What saving twice must leave exactly as it was: the file without what each save stamps."""

    adapter: Callable[[str, str], App]
    """The app's adapter, over its CLI at a version."""

    unsupported: frozenset[str] = frozenset()
    """The features the pinned release is known not to keep, which the matrix says and Nightly
    expects to fail: a feature that fails outside them, or passes inside them, turns it red."""

    hostile: Mapping[str, Callable[[], bytes]] = field(
        default_factory=dict[str, Callable[[], bytes]]
    )
    """Files made to break this app's format, such as a zip bomb, beside those every app is
    given: each must end in a typed failure within its deadline."""

    def source(self, feature: str) -> bytes:
        """The corpus' file for a feature."""
        return (self.folder / f"{feature}{self.extension}").read_bytes()

    def hostile_names(self) -> list[str]:
        """Every hostile file's name: those every app is given, and the app's own."""
        return sorted({*GIVEN, *self.hostile})

    def hostile_file(self, name: str) -> bytes:
        """A hostile file, made when it is asked for, as some are large once inflated."""
        if name in self.hostile:
            return self.hostile[name]()
        whole = self.source(min(self.makers))
        return {
            "empty": b"",
            "noise": random.Random(0).randbytes(1 << 16),
            "truncated": whole[: len(whole) // 2],
        }[name]


def pinned(app: str) -> str:
    """The version of the release `scripts/craft` pins for an app, which its CLI must be."""
    return re.findall(rf"{app}-web-(\S+)\.zip", (PINS / f"{app}.sha256").read_text())[0]
