"""Verdicts: what an evaluator returns."""

from typing import Annotated, Self

from pydantic import BaseModel, Field, model_validator

__all__ = ["Confidence", "Verdict"]

type Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
"""A probability that a field's value is right, from 0 to 1."""


class Verdict[V: BaseModel](BaseModel, frozen=True):
    """An evaluator's judgement of one input: a value of the verdict type, and how it was made.

    The value is an instance of the verdict type, which can be any Pydantic model, typically a
    feedback type people also give. Everything else records how far to trust it and where it
    came from, so verdicts from different evaluators, or different versions of one, never mix.

    Attributes:
        value: The verdict itself.
        confidence: The probability that each field's value is right, for the fields the
            evaluator has one for: decision models report them, most judges do not.
        evaluator: The evaluator's name.
        version: The evaluator's version. A trained judge's version is a hash of its program.
        latency: Wall-clock seconds the evaluation took.
        cost: What the evaluation cost in US dollars, when the evaluator knows.
        trace_id: The OpenTelemetry trace the evaluation ran in, as 32 hex digits, when there
            was one.
    """

    value: V
    confidence: dict[str, Confidence] = Field(default_factory=dict[str, float])
    evaluator: str
    version: str
    latency: Annotated[float, Field(ge=0.0)] = 0.0
    cost: Annotated[float, Field(ge=0.0)] | None = None
    trace_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")] | None = None

    @model_validator(mode="after")
    def _confidence_is_per_field(self) -> Self:
        unknown = sorted(set(self.confidence) - set(type(self.value).model_fields))
        if unknown:
            raise ValueError(f"confidence for fields the verdict does not have: {unknown}")
        return self
