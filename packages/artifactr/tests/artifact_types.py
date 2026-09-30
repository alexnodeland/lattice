"""Artifact and feedback types shared by the tests and the conformance fixtures."""

from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Self

from pydantic import BaseModel, Field

from artifactr.core import Artifact, Feedback, MarkdownArtifact, WritePolicy


class Note(MarkdownArtifact, name="note"):
    """A Markdown note; agents edit it directly."""

    title: str = ""


class Item(BaseModel):
    title: str
    done: bool = False


class Checklist(Artifact, name="checklist"):
    """A checklist; agents must propose changes to it."""

    write_policy: ClassVar[WritePolicy] = "propose"

    title: str = ""
    items: dict[str, Item] = Field(default_factory=dict)

    def describe_change(self, before: Self) -> str | None:
        checked = [
            item.title
            for key, item in self.items.items()
            if item.done and key in before.items and not before.items[key].done
        ]
        return f"checked {', '.join(repr(title) for title in checked)}" if checked else None


class Counter(Artifact, name="counter"):
    """A number, to exercise validation that normalizes data."""

    count: int = 0


class Helpfulness(Feedback, name="helpfulness", targets={"turn", "thread", "message"}):
    """A rating of how helpful the agent was."""

    rating: Annotated[int, Field(ge=1, le=5)]
    reason: str | None = None


class Verdict(StrEnum):
    RIGHT = "right"
    WRONG = "wrong"


class Accuracy(Feedback, name="accuracy", targets={"artifact"}):
    """Whether an artifact version is correct."""

    correct: bool
    verdict: Verdict = Verdict.RIGHT
    tone: Literal["formal", "casual"] = "formal"
    confidence: Annotated[float, Field(ge=0, le=1)] = 1.0
