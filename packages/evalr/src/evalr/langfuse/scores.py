"""Langfuse scores and score configs, as a ``ScoreSink`` and a ``ScoreConfigStore``."""

import asyncio
import re
from collections.abc import Sequence
from typing import Any, assert_never

from langfuse import Langfuse
from langfuse.api import ConfigCategory, ScoreConfigDataType

from evalr.core import Score, ScoreConfig

__all__ = ["LangfuseScoreConfigStore", "LangfuseScoreSink"]

_CONFIG_NAME = re.compile(r"^[A-Za-z0-9_ .()-]{1,35}$")
"""The score config names Langfuse accepts."""

_PAGE = 100


class LangfuseScoreSink:
    """Records scores in Langfuse, on the traces or sessions they judge.

    It records evaluators' scores and the libraries' mirrors of people's feedback alike. Each
    score keeps its id (Langfuse's ``score_id``), so recording a score again replaces it, and its
    span (Langfuse's observation) and timestamp, when it has them. A yes or no is sent as 1 or 0,
    and the score's ``metadata`` (its source, the evaluator, its version and the confidence)
    becomes Langfuse's. Langfuse sends scores in the background; ``flush`` waits for them.
    """

    def __init__(self, client: Langfuse) -> None:
        """Use a Langfuse client.

        Args:
            client: The application's client.
        """
        self.client = client

    async def record(self, scores: Sequence[Score], /) -> None:
        """Queue the scores for Langfuse.

        Raises:
            ValueError: A score has neither a trace nor a session, one of which Langfuse needs to
                attach it to; none of the scores is queued.
        """
        unattached = sorted({s.name for s in scores if s.trace_id is None and s.session_id is None})
        if unattached:
            raise ValueError(
                f"Langfuse attaches scores to traces or sessions, and {unattached} have neither"
            )
        await asyncio.to_thread(self._record, scores)

    async def flush(self) -> None:
        """Wait until Langfuse has sent everything queued."""
        await asyncio.to_thread(self.client.flush)

    def _record(self, scores: Sequence[Score]) -> None:
        for score in scores:
            match score.data_type:
                case "NUMERIC" | "BOOLEAN" as data_type:
                    self.client.create_score(
                        name=score.name,
                        value=float(score.value),
                        trace_id=score.trace_id,
                        observation_id=score.span_id,
                        session_id=score.session_id,
                        score_id=score.id,
                        data_type=data_type,
                        metadata=score.metadata,
                        timestamp=score.timestamp,
                    )
                case "CATEGORICAL" | "TEXT" as data_type:
                    self.client.create_score(
                        name=score.name,
                        value=str(score.value),
                        trace_id=score.trace_id,
                        observation_id=score.span_id,
                        session_id=score.session_id,
                        score_id=score.id,
                        data_type=data_type,
                        metadata=score.metadata,
                        timestamp=score.timestamp,
                    )
                case _:
                    assert_never(score.data_type)


class LangfuseScoreConfigStore:
    """Keeps score configs in Langfuse, so it knows each score's type, range and choices.

    Langfuse's API is synchronous, so its calls run in a worker thread.
    """

    def __init__(self, client: Langfuse) -> None:
        """Use a Langfuse client.

        Args:
            client: The application's client.
        """
        self.client = client

    async def names(self) -> set[str]:
        """Return the names of Langfuse's score configs, archived or not."""
        return await asyncio.to_thread(self._names)

    async def create(self, config: ScoreConfig, /) -> None:
        """Create a score config in Langfuse.

        Raises:
            ValueError: The name is not one Langfuse accepts: at most 35 letters, digits, spaces
                and ``_.()-``. Shorten the type's name or the field's.
        """
        if not _CONFIG_NAME.match(config.name):
            raise ValueError(
                f"Langfuse does not accept the score config name {config.name!r}: shorten the "
                "type's name or the field's, to 35 characters at most"
            )
        options: dict[str, Any] = {}
        if config.categories:
            options["categories"] = [
                ConfigCategory(label=label, value=index)
                for index, label in enumerate(config.categories)
            ]
        if config.minimum is not None:
            options["min_value"] = config.minimum
        if config.maximum is not None:
            options["max_value"] = config.maximum
        if config.description:
            options["description"] = config.description
        await asyncio.to_thread(
            self.client.api.score_configs.create,
            name=config.name,
            data_type=ScoreConfigDataType(config.data_type),
            **options,
        )

    def _names(self) -> set[str]:
        names: set[str] = set()
        page = 1
        while True:
            configs = self.client.api.score_configs.get(page=page, limit=_PAGE)
            names.update(config.name for config in configs.data)
            if page >= (configs.meta.total_pages or 1):
                return names
            page += 1
