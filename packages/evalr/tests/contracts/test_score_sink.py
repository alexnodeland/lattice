"""Every score sink adapter meets the ScoreSink contract."""

from collections.abc import Sequence

import pytest

from evalr.contracts import ContractViolation, check_score_sink
from evalr.core import Score
from evalr.memory import InMemoryScoreSink


async def test_the_in_memory_sink_meets_the_contract() -> None:
    sink = InMemoryScoreSink()

    async def recorded() -> Sequence[Score]:
        return list(sink.scores.values())

    await check_score_sink(sink, recorded)


class Appending:
    def __init__(self) -> None:
        self.held: list[Score] = []

    async def record(self, scores: Sequence[Score], /) -> None:
        self.held.extend(scores)


class Stubborn(InMemoryScoreSink):
    async def record(self, scores: Sequence[Score], /) -> None:
        for score in scores:
            self.scores.setdefault(score.id, score)


class Lossy(InMemoryScoreSink):
    async def record(self, scores: Sequence[Score], /) -> None:
        await super().record(scores[1:])


@pytest.mark.parametrize(
    ("broken", "message"),
    [
        (Appending(), "replace it, not add another"),
        (Stubborn(), "latest value recorded must be kept"),
        (Lossy(), "every score recorded, and only those"),
    ],
    ids=["appending", "stubborn", "lossy"],
)
async def test_a_broken_sink_fails_the_contract(
    broken: Appending | InMemoryScoreSink, message: str
) -> None:
    async def recorded() -> Sequence[Score]:
        return broken.held if isinstance(broken, Appending) else list(broken.scores.values())

    with pytest.raises(ContractViolation, match=message):
        await check_score_sink(broken, recorded)
