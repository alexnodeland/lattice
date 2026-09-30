import pytest
from pydantic import BaseModel, Field
from pydantic.fields import FieldInfo

from evalr.core import UnsupportedField, verdict_fields
from evalr.dspy import default_instructions, judge_signature
from evalr.dspy.signatures import describe

from .models import Helpfulness, Thread, Tone


def desc(info: FieldInfo) -> object:
    extra = info.json_schema_extra
    assert isinstance(extra, dict)
    return extra["desc"]


def test_an_input_per_input_field_and_an_output_per_verdict_field() -> None:
    signature = judge_signature(Thread, Helpfulness)
    assert list(signature.input_fields) == ["request", "reply"]
    assert list(signature.output_fields) == [
        "rating",
        "resolved",
        "category",
        "tone",
        "share",
        "reason",
    ]
    assert {n: desc(i) for n, i in signature.fields.items()} == {
        "request": "What the person asked for",
        "reply": "reply",
        "rating": "How much the reply helped (a whole number from 1 to 5)",
        "resolved": "The request was fully addressed",
        "category": "category",
        "tone": "tone (may be left empty)",
        "share": "share (a number from 0 to 1)",
        "reason": "reason (may be left empty)",
    }
    assert signature.input_fields["request"].annotation is str
    assert signature.output_fields["rating"].annotation is int
    assert signature.output_fields["tone"].annotation == Tone | None


def test_instructions_come_from_the_types_unless_given() -> None:
    assert judge_signature(Thread, Helpfulness).instructions == (
        "Read the Thread and judge it, giving a Helpfulness.\n\n"
        "Whether the reply helped the person."
    )
    assert (
        judge_signature(Thread, Helpfulness, instructions="Be strict.").instructions == "Be strict."
    )

    class Plain(BaseModel):
        ok: bool

    assert default_instructions(Thread, Plain) == "Read the Thread and judge it, giving a Plain."


def test_half_bounded_numbers_say_which_bound() -> None:
    class Measures(BaseModel):
        low: float = Field(ge=0.5)
        high: int = Field(le=10)
        free: float

    assert [describe(f) for f in verdict_fields(Measures)] == [
        "low (a number of at least 0.5)",
        "high (a number of at most 10)",
        "free",
    ]


def test_field_names_must_be_distinct_and_not_reserved() -> None:
    class Clash(BaseModel):
        reply: str

    class Thinking(BaseModel):
        reasoning: str

    with pytest.raises(ValueError, match=r"\['reply'\]"):
        judge_signature(Thread, Clash)
    with pytest.raises(ValueError, match=r"\['reasoning'\]"):
        judge_signature(Thread, Thinking)


def test_unjudgeable_verdicts_are_rejected() -> None:
    class Listy(BaseModel):
        tags: list[str]

    with pytest.raises(UnsupportedField):
        judge_signature(Thread, Listy)
