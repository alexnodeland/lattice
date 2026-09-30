"""Every score config store adapter meets the ScoreConfigStore contract."""

import pytest

from evalr.contracts import ContractViolation, check_score_config_store
from evalr.core import ScoreConfig
from evalr.memory import InMemoryScoreConfigStore


async def test_the_in_memory_store_meets_the_contract() -> None:
    await check_score_config_store(InMemoryScoreConfigStore())


class Seeded(InMemoryScoreConfigStore):
    def __init__(self) -> None:
        super().__init__()
        self.configs["left.over"] = ScoreConfig("left.over", "left", "over", "TEXT")


class Forgetful(InMemoryScoreConfigStore):
    async def names(self) -> set[str]:
        return set(list(self.configs)[1:])


class FirstOnly(InMemoryScoreConfigStore):
    async def create(self, config: ScoreConfig, /) -> None:
        if not self.configs:
            await super().create(config)


@pytest.mark.parametrize(
    ("broken", "message"),
    [
        (Seeded(), "must list no names"),
        (Forgetful(), "listed by its name, and only it"),
        (FirstOnly(), "every config created, and only those"),
    ],
    ids=["seeded", "forgetful", "first-only"],
)
async def test_a_broken_store_fails_the_contract(
    broken: InMemoryScoreConfigStore, message: str
) -> None:
    with pytest.raises(ContractViolation, match=message):
        await check_score_config_store(broken)
