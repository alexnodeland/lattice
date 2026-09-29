"""What the contract suites share: the violation, assertions and example types."""

from collections.abc import Awaitable
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from evalr.core import Dataset, Example

__all__ = ["ContractInput", "ContractVerdict", "ContractViolation", "contract_dataset"]


class ContractViolation(AssertionError):
    """An adapter behaves differently from its port's contract."""


def require(condition: bool, message: str) -> None:
    """Raise ``ContractViolation`` with the message unless the condition holds."""
    if not condition:
        raise ContractViolation(message)


async def expect_raises(error: type[BaseException], call: Awaitable[object], message: str) -> None:
    """Raise ``ContractViolation`` with the message unless the call raises ``error``."""
    try:
        await call
    except error:
        return
    raise ContractViolation(message)


class ContractInput(BaseModel):
    """The input type of the examples the contract suites use."""

    title: str
    messages: list[str]


class ContractVerdict(BaseModel):
    """A verdict type with a field of every kind, for the contract suites."""

    rating: Annotated[int, Field(ge=1, le=5, description="How good it is")]
    resolved: bool
    tone: Literal["warm", "neutral", "cold"] | None = None
    share: float = Field(default=0.5, ge=0.0, le=1.0)
    reason: str | None = None


def contract_example(i: int) -> Example[ContractInput, ContractVerdict]:
    """A deterministic example, different for every ``i``."""
    return Example[ContractInput, ContractVerdict](
        id=f"example-{i}",
        input=ContractInput(title=f"Thread {i}", messages=[f"question {i}", f"answer {i} é"]),
        verdict=ContractVerdict(
            rating=1 + i % 5,
            resolved=i % 2 == 0,
            tone=("warm", "neutral", "cold", None)[i % 4],
            share=(i % 10) / 10,
            reason=f"because {i}" if i % 3 else None,
        ),
        reference={"answer": f"answer {i}", "steps": [i, i + 1]} if i % 2 else None,
        trace_id=f"{i:032x}",
        metadata={"source": "contract", "index": i},
    )


def contract_dataset(name: str, count: int = 6) -> Dataset[ContractInput, ContractVerdict]:
    """A dataset of ``count`` contract examples."""
    return Dataset(
        name,
        (contract_example(i) for i in range(count)),
        input_type=ContractInput,
        verdict_type=ContractVerdict,
        description="Examples the evalr contract suite saves and loads",
    )
