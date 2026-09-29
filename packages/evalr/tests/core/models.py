"""Verdict and input types shared by the core tests."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from evalr.core import HandOff, Verdict, get_tracer, judging


class Thread(BaseModel):
    messages: list[str]


class Helpfulness(BaseModel):
    rating: Annotated[int, Field(ge=1, le=5, description="How much the reply helped")]
    resolved: bool = Field(description="The request was fully addressed")
    category: Literal["billing", "bug", "other"] = "other"
    reason: str | None = None


class Scripted:
    """An evaluator with fixed answers and confidence, keyed by the thread's first message."""

    def __init__(
        self,
        answers: dict[str, tuple[Helpfulness, dict[str, float]]],
        *,
        name: str = "scripted",
        version: str = "1",
        hand_off: frozenset[str] = frozenset(),
    ) -> None:
        self.answers = answers
        self.name = name
        self.version = version
        self.hand_off = hand_off
        self.verdict_type = Helpfulness
        self.calls = 0

    async def evaluate(self, input: Thread, /) -> Verdict[Helpfulness]:
        self.calls += 1
        key = input.messages[0]
        if key in self.hand_off:
            raise HandOff(f"unsure about {key}")
        value, confidence = self.answers[key]
        with judging(
            get_tracer(), evaluator=self.name, version=self.version, verdict_type=Helpfulness
        ) as run:
            return run.verdict(value, confidence=confidence)
