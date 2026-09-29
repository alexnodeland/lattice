"""The ``ScoreSink`` and ``ScoreConfigStore`` contracts."""

import uuid
from collections.abc import Awaitable, Callable, Sequence

from evalr.contracts.support import ContractVerdict, require
from evalr.core import (
    SCORE_NAMESPACE,
    Score,
    ScoreConfigStore,
    ScoreSink,
    Verdict,
    score_configs,
    scores,
)

__all__ = ["check_score_config_store", "check_score_sink"]


def _verdict(i: int) -> Verdict[ContractVerdict]:
    return Verdict(
        value=ContractVerdict(rating=1 + i % 5, resolved=i % 2 == 0, tone="warm", reason=f"r{i}"),
        confidence={"rating": 0.75, "resolved": 0.5},
        evaluator="evalr-contract",
        version="1",
        trace_id=f"{i + 1:032x}",
    )


def _feedback() -> Score:
    """A person's score on a session, as the libraries' feedback mirrors send."""
    return Score(
        id=str(uuid.uuid5(SCORE_NAMESPACE, "evalr-contract|feedback")),
        name="contract_verdict.rating",
        value=4.0,
        data_type="NUMERIC",
        session_id="evalr-contract-session",
        source={"actor": "evalr-contract-person"},
    )


async def check_score_sink(
    sink: ScoreSink, recorded: Callable[[], Awaitable[Sequence[Score]]]
) -> None:
    """Check that a score sink keeps one score per id, the latest recorded, on its trace or session.

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
    feedback = _feedback()
    await sink.record(first)
    await sink.record(first)
    await sink.record(second)
    await sink.record([feedback])
    changed = first[0].model_copy(update={"value": 5.0})
    await sink.record([changed])

    expected = {score.id: score for score in [*first, *second, feedback, changed]}
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
            (kept.name, kept.value, kept.data_type, kept.trace_id, kept.session_id)
            == (score.name, score.value, score.data_type, score.trace_id, score.session_id),
            f"{score.name}: the latest value recorded must be kept, with its type, trace and "
            "session",
        )


async def check_score_config_store(store: ScoreConfigStore) -> None:
    """Check that a score config store lists every config created in it, by name.

    Args:
        store: The store to check, holding no configs yet.

    Raises:
        ContractViolation: The store behaves differently from the ``ScoreConfigStore`` contract.
    """
    require(not await store.names(), "a store holding no configs must list no names")
    first, *rest = score_configs(ContractVerdict, type_name="evalr_contract")
    await store.create(first)
    require(
        set(await store.names()) == {first.name},
        "a config created must be listed by its name, and only it",
    )
    for config in rest:
        await store.create(config)
    require(
        set(await store.names()) == {first.name, *(config.name for config in rest)},
        "every config created, and only those, must be listed by name",
    )
