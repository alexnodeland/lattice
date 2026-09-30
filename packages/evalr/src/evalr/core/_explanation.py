"""A verdict's text as the explanation of its other scores, for the sinks that attach one."""

from collections.abc import Iterable

from evalr.core.scores import Score


def explanation(scores: Iterable[Score]) -> str:
    """A verdict's text as the explanation of its scores: a ``field: text`` line per text score."""
    return "\n".join(
        f"{score.name.rsplit('.', 1)[-1]}: {score.value}"
        for score in scores
        if score.data_type == "TEXT"
    )
