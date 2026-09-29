"""The ``ScoreSink`` contract."""

from collections.abc import Awaitable, Callable, Sequence

from evalr.contracts.support import ContractVerdict, require
from evalr.core import Score, ScoreSink, Verdict, scores

__all__ = ["check_score_sink"]


def _verdict(i: int) -> Verdict[ContractVerdict]:
    return Verdict(
        value=ContractVerdict(rating=1 + i % 5, resolved=i % 2 == 0, tone="warm", reason=f"r{i}"),
        confidence={"rating": 0.75, "resolved": 0.5},
        evaluator="evalr-contract",
        version="1",
        trace_id=f"{i + 1:032x}",
    )


async def check_score_sink(
    sink: ScoreSink, recorded: Callable[[], Awaitable[Sequence[Score]]]
) -> None:
    """Check that a score sink keeps one score per id, the latest recorded.

    A score sink has no reads, so the caller says how to see what it recorded: the in-memory
    sink's scores, or what a backend's fake received.

    Args:
        sink: The sink to check, holding no scores yet.
        recorded: Returns the scores the sink holds, as ``Score`` values.

    Raises:
        ContractViolation: The sink behaves differently from the ``ScoreSink`` contract.
    """
    first = scores(_verdict(1))
    second = scores(_verdict(2), subject="contract-subject")
    await sink.record(first)
    await sink.record(first)
    await sink.record(second)
    changed = first[0].model_copy(update={"value": 5.0})
    await sink.record([changed])

    expected = {score.id: score for score in [*first, *second, changed]}
    held = list(await recorded())
    require(
        len(held) == len({score.id for score in held}),
        "recording a score again must replace it, not add another",
    )
    by_id = {score.id: score for score in held}
    require(set(by_id) == set(expected), "every score recorded, and only those, must be kept")
    for score_id, score in expected.items():
        kept = by_id[score_id]
        require(
            (kept.name, kept.value, kept.data_type, kept.trace_id)
            == (score.name, score.value, score.data_type, score.trace_id),
            f"{score.name}: the latest value recorded must be kept, with its type and trace",
        )
