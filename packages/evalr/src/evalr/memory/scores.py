"""An in-memory score sink and score config store."""

from collections.abc import Sequence

from evalr.core import Score, ScoreConfig

__all__ = ["InMemoryScoreConfigStore", "InMemoryScoreSink"]


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


class InMemoryScoreConfigStore:
    """Keeps score configs by name.

    Attributes:
        configs: The configs created, by name.
    """

    def __init__(self) -> None:
        """Start empty."""
        self.configs: dict[str, ScoreConfig] = {}

    async def names(self) -> set[str]:
        """Return the names of the configs created."""
        return set(self.configs)

    async def create(self, config: ScoreConfig, /) -> None:
        """Keep a config.

        Raises:
            ValueError: The store has a config of that name, so the caller created one it should
                have looked for first.
        """
        if config.name in self.configs:
            raise ValueError(f"a score config named {config.name!r} exists already")
        self.configs[config.name] = config
