"""An in-memory score sink."""

from collections.abc import Sequence

from evalr.core import Score

__all__ = ["InMemoryScoreSink"]


class InMemoryScoreSink:
    """Keeps the latest score of each id.

    Attributes:
        scores: The recorded scores, by id.
    """

    def __init__(self) -> None:
        """Start empty."""
        self.scores: dict[str, Score] = {}

    async def record(self, scores: Sequence[Score], /) -> None:
        """Keep the scores, replacing any with the same id."""
        for score in scores:
            self.scores[score.id] = score
