"""Every feedback source meets the FeedbackSource contract."""

from collections.abc import AsyncIterator
from typing import cast

import pytest
from pydantic import BaseModel

from evalr.contracts import ContractInput, ContractVerdict, ContractViolation, check_feedback_source
from evalr.contracts.support import contract_example
from evalr.core import Example, UnsupportedField
from evalr.memory import InMemoryFeedbackSource

Ex = Example[ContractInput, ContractVerdict]


def source(examples: list[Ex]) -> InMemoryFeedbackSource[ContractInput, ContractVerdict]:
    return InMemoryFeedbackSource(examples, input_type=ContractInput, verdict_type=ContractVerdict)


async def test_the_in_memory_source_meets_the_contract() -> None:
    await check_feedback_source(source([contract_example(i) for i in range(5)]))


async def test_duplicate_ids_fail() -> None:
    with pytest.raises(ContractViolation, match="unique"):
        await check_feedback_source(source([contract_example(1), contract_example(1)]))


async def test_feedback_without_a_verdict_fails() -> None:
    unlabelled = contract_example(1).model_copy(update={"verdict": None})
    with pytest.raises(ContractViolation, match="example-1: the verdict must be a ContractVerdict"):
        await check_feedback_source(source([unlabelled]))


async def test_an_input_of_the_wrong_type_fails() -> None:
    class Other(BaseModel):
        x: int = 0

    wrong = cast(Ex, Example[Other, ContractVerdict](id="w", input=Other()))
    with pytest.raises(ContractViolation, match="w: the input must be a ContractInput"):
        await check_feedback_source(source([wrong]))


class Shifting:
    """Yields a new example every time it is iterated."""

    def __init__(self) -> None:
        self.calls = 0

    @property
    def input_type(self) -> type[ContractInput]:
        return ContractInput

    @property
    def verdict_type(self) -> type[ContractVerdict]:
        return ContractVerdict

    async def examples(self) -> AsyncIterator[Ex]:
        self.calls += 1
        yield contract_example(self.calls)


async def test_an_unstable_source_fails() -> None:
    with pytest.raises(ContractViolation, match="same examples"):
        await check_feedback_source(Shifting())


async def test_an_unjudgeable_feedback_type_fails() -> None:
    class Listy(BaseModel):
        tags: list[str]

    listy = InMemoryFeedbackSource[ContractInput, Listy](
        [], input_type=ContractInput, verdict_type=Listy
    )
    with pytest.raises(UnsupportedField):
        await check_feedback_source(listy)
