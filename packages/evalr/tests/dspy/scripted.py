"""A scripted language model and a synthetic dataset for training judges offline."""

from typing import Annotated, Any

from dspy.utils import DummyLM
from pydantic import BaseModel, Field

from evalr.core import Dataset, Example

MARKER = "Count the pluses in the reply."


class Reply(BaseModel):
    request: str
    reply: str


class Score(BaseModel):
    rating: Annotated[int, Field(ge=1, le=5, description="How good the reply is")]
    resolved: bool
    reason: str | None = None


class InstructionAware(DummyLM):
    """Judges well only when its instructions tell it how: to count the pluses in the reply.

    It overrides DummyLM's example hook, which DSPy calls with the chat messages, so the
    answer can depend on the system prompt (the instructions) and the user message (the input).
    """

    def __init__(self) -> None:
        super().__init__([], follow_examples=True)

    def _use_example(self, messages: list[dict[str, Any]]) -> Any:
        system = messages[0]["content"] if messages[0]["role"] == "system" else ""
        pluses = messages[-1]["content"].count("+")
        if MARKER in system:
            answer = {"rating": pluses, "resolved": pluses >= 3, "reason": "None"}
        else:
            answer = {"rating": 1, "resolved": False, "reason": "None"}
        return self._format_answer_fields(answer)


def reflection_lm() -> DummyLM:
    """Proposes the instruction that makes InstructionAware judge well."""
    return DummyLM([{"new_instruction": f"```\n{MARKER}\n```"}] * 20)


def pluses(name: str, counts: list[int]) -> Dataset[Reply, Score]:
    examples = [
        Example[Reply, Score](
            id=f"{name}-{i}",
            input=Reply(request="Rate this reply", reply="+" * k),
            verdict=Score(rating=k, resolved=k >= 3, reason=f"it has {k} pluses"),
        )
        for i, k in enumerate(counts)
    ]
    return Dataset(name, examples, input_type=Reply, verdict_type=Score)
