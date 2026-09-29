"""Langfuse scores as a ``ScoreSink``."""

import asyncio
from collections.abc import Sequence

from langfuse import Langfuse

from evalr.core import Score

__all__ = ["LangfuseScoreSink"]


class LangfuseScoreSink:
    """Records scores in Langfuse, on the traces they judge.

    Each score keeps its id (Langfuse's ``score_id``), so recording a verdict again replaces
    its scores. The evaluator, its version and the confidence go in the score's metadata.
    Langfuse sends scores in the background; ``flush`` waits for them.
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
            ValueError: A score has no trace, which Langfuse needs to attach it to.
        """
        untraced = sorted({s.name for s in scores if s.trace_id is None})
        if untraced:
            raise ValueError(f"Langfuse attaches scores to traces, and {untraced} have none")
        await asyncio.to_thread(self._record, scores)

    async def flush(self) -> None:
        """Wait until Langfuse has sent everything queued."""
        await asyncio.to_thread(self.client.flush)

    def _record(self, scores: Sequence[Score]) -> None:
        for score in scores:
            if isinstance(score.value, str):
                self.client.create_score(
                    name=score.name,
                    value=score.value,
                    trace_id=score.trace_id,
                    score_id=score.id,
                    data_type="TEXT" if score.data_type == "TEXT" else "CATEGORICAL",
                    metadata=score.metadata,
                )
            else:
                self.client.create_score(
                    name=score.name,
                    value=float(score.value),
                    trace_id=score.trace_id,
                    score_id=score.id,
                    data_type="BOOLEAN" if score.data_type == "BOOLEAN" else "NUMERIC",
                    metadata=score.metadata,
                )
