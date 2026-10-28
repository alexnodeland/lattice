"""A fake app that names the format of the files it makes, and may make none from nothing."""

from collections.abc import Sequence

from artifactr.files.app import AppCommand, AppFailed, FakeApp
from artifactr.files.app import Applied as Made


class Naming(FakeApp):
    """A fake app whose files are of the format it names, if any, and that may make none blank."""

    def __init__(self, media_type: str | None = None, *, blank: bool = True) -> None:
        super().__init__()
        self.media_type = media_type
        self.blank = blank
        self.made = 0

    async def apply(
        self, source: bytes | None, commands: Sequence[AppCommand], *, deadline: float
    ) -> Made:
        if source is None and not self.blank:
            raise AppFailed("refused", "it makes no file from nothing")
        self.made += 1
        applied = await super().apply(source, commands, deadline=deadline)
        named = applied.inspection.model_copy(update={"media_type": self.media_type})
        return Made(content=applied.content, inspection=named)
