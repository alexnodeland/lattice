from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal

import annotated_types
import pytest
from pydantic import BaseModel, Field, create_model

from evalr import FieldKind, UnsupportedField, VerdictField, verdict_fields


class Tone(Enum):
    WARM = "warm"
    COLD = "cold"


class Helpfulness(BaseModel):
    rating: Annotated[int, Field(ge=1, le=5, description="How much the reply helped")]
    resolved: bool = Field(description="The request was fully addressed")
    category: Literal["billing", "bug", "other"]
    tone: Tone | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    count: int
    reason: str | None = None


def test_fields_are_described_in_declaration_order() -> None:
    assert verdict_fields(Helpfulness) == (
        VerdictField(
            "rating", FieldKind.ORDINAL, "How much the reply helped", lower=1.0, upper=5.0
        ),
        VerdictField(
            "resolved",
            FieldKind.BINARY,
            "The request was fully addressed",
            choices=(False, True),
        ),
        VerdictField("category", FieldKind.CATEGORICAL, choices=("billing", "bug", "other")),
        VerdictField(
            "tone",
            FieldKind.CATEGORICAL,
            choices=(Tone.WARM, Tone.COLD),
            optional=True,
            required=False,
        ),
        VerdictField("confidence", FieldKind.NUMERIC, lower=0.0, upper=1.0),
        VerdictField("count", FieldKind.NUMERIC),
        VerdictField("reason", FieldKind.TEXT, optional=True, required=False),
    )


def test_text_fields_are_not_scored() -> None:
    scored = [f.name for f in verdict_fields(Helpfulness) if f.scored]
    assert scored == ["rating", "resolved", "category", "tone", "confidence", "count"]


def test_constraints_inside_an_optional_are_found() -> None:
    class Nested(BaseModel):
        a: Annotated[int, Field(ge=0, le=3, description="inner")] | None = None
        b: Annotated[int, annotated_types.Interval(ge=1, le=7)] | None = None
        c: Annotated[Annotated[int, Field(ge=2)], Field(le=4)]

    a, b, c = verdict_fields(Nested)
    assert (a.kind, a.lower, a.upper, a.description, a.optional) == (
        FieldKind.ORDINAL,
        0.0,
        3.0,
        "inner",
        True,
    )
    assert (b.kind, b.lower, b.upper) == (FieldKind.ORDINAL, 1.0, 7.0)
    assert (c.kind, c.lower, c.upper) == (FieldKind.ORDINAL, 2.0, 4.0)


def test_an_integer_needs_both_bounds_to_be_ordinal() -> None:
    class Half(BaseModel):
        low: int = Field(ge=0)
        high: int = Field(le=10)

    assert [(f.kind, f.lower, f.upper) for f in verdict_fields(Half)] == [
        (FieldKind.NUMERIC, 0.0, None),
        (FieldKind.NUMERIC, None, 10.0),
    ]


def test_exclusive_bounds_become_inclusive_for_integers_only() -> None:
    class Exclusive(BaseModel):
        whole: int = Field(gt=0, lt=6)
        real: float = Field(gt=0.0, lt=1.0)

    whole, real = verdict_fields(Exclusive)
    assert (whole.kind, whole.lower, whole.upper) == (FieldKind.ORDINAL, 1.0, 5.0)
    assert (real.kind, real.lower, real.upper) == (FieldKind.NUMERIC, 0.0, 1.0)


def test_other_constraints_and_non_numeric_bounds_are_ignored() -> None:
    class Odd(BaseModel):
        steps: Annotated[int, Field(multiple_of=2)]
        exact: Annotated[float, annotated_types.Ge(Decimal(1))]

    steps, exact = verdict_fields(Odd)
    assert (steps.kind, steps.lower, steps.upper) == (FieldKind.NUMERIC, None, None)
    assert (exact.kind, exact.lower) == (FieldKind.NUMERIC, None)


@pytest.mark.parametrize(
    "annotation",
    [list[str], dict[str, int], int | str, bytes],
    ids=["list", "dict", "union", "bytes"],
)
def test_unjudgeable_fields_are_rejected(annotation: object) -> None:
    bad = create_model("Bad", field=(annotation, ...))
    with pytest.raises(UnsupportedField, match=r"Bad\.field"):
        verdict_fields(bad)


def test_nested_models_are_rejected() -> None:
    class Inner(BaseModel):
        x: int

    class Outer(BaseModel):
        inner: Inner

    with pytest.raises(UnsupportedField, match=r"Outer\.inner"):
        verdict_fields(Outer)
