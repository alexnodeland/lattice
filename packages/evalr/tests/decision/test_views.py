from enum import Enum, IntEnum
from typing import Annotated, Literal

import pytest
from pydantic import BaseModel, Field

from evalr.core import UnsupportedField
from evalr.decision import decision_view

from .models import Helpfulness, Tone


def test_the_view_keeps_what_a_decision_model_can_fill() -> None:
    view = decision_view(Helpfulness)
    assert view.decided == ("rating", "resolved", "category", "tone", "share")
    assert view.left_out == ("reason",)
    assert view.model.__name__ == "HelpfulnessDecision"
    assert view.model.__doc__ == "Whether the reply helped the person."
    fields = view.model.model_fields
    assert fields["rating"].annotation == Literal[1, 2, 3, 4, 5]
    assert fields["rating"].description == "How much the reply helped"
    assert fields["resolved"].annotation is bool
    assert fields["category"].default == "other"
    assert fields["tone"].annotation == Tone | None
    assert view.model.model_json_schema()["properties"]["share"]["maximum"] == 1.0


def test_an_optional_scale_stays_optional() -> None:
    class Maybe(BaseModel):
        stars: Annotated[int, Field(ge=0, le=2)] | None = None

    (stars,) = decision_view(Maybe).model.model_fields.values()
    assert stars.annotation == Literal[0, 1, 2] | None


class Level(IntEnum):
    LOW = 1
    HIGH = 2


class Mixed(Enum):
    ONE = 1
    TWO = "two"


class Undecidable(BaseModel):
    maybe: bool | None = None
    note: str = "n/a"
    count: int = 0
    ratio: float | None = None
    offset: float = Field(default=0.5, ge=0.5, le=1.0)
    flag: Literal[True, False] = True
    mixed: Mixed = Mixed.ONE
    single: Literal["only"] = "only"
    wide: Annotated[int, Field(ge=0, le=1000)] = 0
    level: Level = Level.LOW


def test_fields_a_decision_model_cannot_fill_are_left_out() -> None:
    view = decision_view(Undecidable)
    assert view.decided == ("level",)
    assert view.left_out == (
        "maybe",
        "note",
        "count",
        "ratio",
        "offset",
        "flag",
        "mixed",
        "single",
        "wide",
    )


def test_a_required_field_that_cannot_be_decided_is_rejected() -> None:
    class Needs(BaseModel):
        ok: bool
        reason: str

    with pytest.raises(UnsupportedField, match=r"Needs\.reason: a decision model cannot fill"):
        decision_view(Needs)


def test_default_factories_are_kept() -> None:
    class Listless(BaseModel):
        ok: bool = Field(default_factory=lambda: True)

    assert decision_view(Listless).model().model_dump() == {"ok": True}
