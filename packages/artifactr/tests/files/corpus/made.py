"""A corpus its app makes: each feature's file a batch of the app's own commands on a blank one.

FilmCraft's, EffectCraft's and SoundCraft's projects are JSON in which their apps write every
field, too many to write by hand and still be read, so each feature's file is what the app's
adapter saves of a batch of its commands on a blank project. The committed files are each
corpus' makers; `python -m tests.files.corpus.<app>.make CLI`, from `packages/artifactr`, writes
them again from the pinned CLI, and each app's live tests hold them to what it makes.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Final

from artifactr.files.app import App, AppCommand

DEADLINE: Final = 60


@dataclass(frozen=True)
class Made:
    """A corpus its app makes: a script of the app's commands for each feature."""

    folder: Path
    extension: str
    scripts: Mapping[str, Sequence[AppCommand]]
    """Each feature, and the commands that make its file from a blank one."""

    def committed(self, feature: str) -> bytes:
        """The feature's file, as the app last made it."""
        return (self.folder / f"{feature}{self.extension}").read_bytes()

    def makers(self) -> dict[str, Callable[[], bytes]]:
        """Each feature, and its committed file: the corpus' makers."""
        return {feature: partial(self.committed, feature) for feature in self.scripts}

    async def make(self, app: App, feature: str) -> bytes:
        """The feature's file, as the app makes it now."""
        return (await app.apply(None, self.scripts[feature], deadline=DEADLINE)).content

    async def write(self, app: App) -> None:
        """Make every feature's file again, and write it beside its script."""
        for feature in self.scripts:
            (self.folder / f"{feature}{self.extension}").write_bytes(await self.make(app, feature))


def step(command: str, /, **args: object) -> AppCommand:
    """One command of a feature's script, by its id, with its parameters."""
    return AppCommand.model_validate({"name": command, "args": args})
