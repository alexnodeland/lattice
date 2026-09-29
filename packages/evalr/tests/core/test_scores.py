import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Literal

import pytest
from pydantic import BaseModel, Field, ValidationError

from evalr import Verdict, scores
from evalr.core import (
    MAX_TEXT,
    SCORE_NAMESPACE,
    Score,
    score_configs,
    score_type_name,
    score_values,
)

from .models import Helpfulness


class Tone(Enum):
    WARM = "warm"
    COLD = "cold"


class TaskCompletion(BaseModel):
    completed: bool
    quality: float = Field(ge=0.0, le=1.0)
    steps: int
    tone: Tone
    level: Literal[1, 2, 3]
    note: str | None = None


def verdict(**overrides: object) -> Verdict[TaskCompletion]:
    fields: dict[str, object] = {
        "completed": True,
        "quality": 0.5,
        "steps": 3,
        "tone": Tone.WARM,
        "level": 2,
        "note": "fine",
    }
    fields.update(overrides)
    return Verdict(
        value=TaskCompletion.model_validate(fields),
        confidence={"completed": 0.9},
        evaluator="judge",
        version="v1",
        trace_id="0af7651916cd43dd8448eb211c80319c",
    )


def test_every_field_with_a_value_becomes_a_typed_score() -> None:
    result = scores(verdict())
    assert [(s.name, s.value, s.data_type) for s in result] == [
        ("task_completion.completed", True, "BOOLEAN"),
        ("task_completion.quality", 0.5, "NUMERIC"),
        ("task_completion.steps", 3.0, "NUMERIC"),
        ("task_completion.tone", "warm", "CATEGORICAL"),
        ("task_completion.level", "2", "CATEGORICAL"),
        ("task_completion.note", "fine", "TEXT"),
    ]
    assert isinstance(result[2].value, float)
    assert {s.trace_id for s in result} == {"0af7651916cd43dd8448eb211c80319c"}
    assert result[0].metadata == {"evaluator": "judge", "version": "v1", "confidence": 0.9}
    assert result[1].metadata == {"evaluator": "judge", "version": "v1"}


def test_empty_fields_give_no_score() -> None:
    assert "task_completion.note" not in {s.name for s in scores(verdict(note=None))}


def test_ids_are_derived_from_the_subject_the_evaluator_and_the_field() -> None:
    first = scores(verdict())
    assert [s.id for s in scores(verdict())] == [s.id for s in first]
    assert first[0].id == str(
        uuid.uuid5(
            SCORE_NAMESPACE,
            "0af7651916cd43dd8448eb211c80319c|judge|v1|task_completion.completed",
        )
    )
    other_subject = scores(verdict(), subject="run-7")
    assert other_subject[0].id != first[0].id
    other_version = scores(verdict().model_copy(update={"version": "v2"}))
    assert other_version[0].id != first[0].id


def test_without_a_trace_or_subject_the_content_keys_the_ids() -> None:
    untraced = verdict().model_copy(update={"trace_id": None})
    assert scores(untraced)[0].id == scores(untraced)[0].id
    assert (
        scores(untraced)[0].id
        != scores(untraced.model_copy(update={"value": verdict(steps=4).value}))[0].id
    )
    assert scores(untraced)[0].trace_id is None


def test_the_type_name_and_trace_can_be_given() -> None:
    result = scores(verdict(), type_name="completion", trace_id="f" * 32)
    assert result[0].name == "completion.completed"
    assert result[0].trace_id == "f" * 32


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Helpfulness", "helpfulness"),
        ("TaskCompletion", "task_completion"),
        ("HTTPError", "http_error"),
        ("Rating5Point", "rating5_point"),
    ],
)
def test_type_names_are_snake_case(name: str, expected: str) -> None:
    assert score_type_name(type(name, (BaseModel,), {})) == expected


def test_scores_of_the_shared_helpfulness_type() -> None:
    value = Helpfulness(rating=4, resolved=False, category="bug")
    result = scores(Verdict(value=value, evaluator="e", version="1"), subject="s")
    assert [s.name for s in result] == [
        "helpfulness.rating",
        "helpfulness.resolved",
        "helpfulness.category",
    ]


def test_empty_text_gives_no_score_and_long_text_is_cut() -> None:
    assert "task_completion.note" not in {s.name for s in scores(verdict(note=""))}
    [note] = [s for s in scores(verdict(note="x" * (MAX_TEXT + 1))) if s.data_type == "TEXT"]
    assert note.value == "x" * MAX_TEXT


def test_values_may_be_a_models_fields_or_its_json() -> None:
    value = verdict().value
    from_fields = score_values(TaskCompletion, dict(value))
    from_json = score_values(TaskCompletion, value.model_dump(mode="json"))
    assert from_fields == from_json
    assert [v for _, v in from_json] == [True, 0.5, 3.0, "warm", "2", "fine"]
    assert score_values(TaskCompletion, {"steps": 4}) == [(score_configs(TaskCompletion)[2], 4.0)]


def test_configs_skip_the_fields_that_cannot_be_scored() -> None:
    class Review(BaseModel):
        tags: list[str]
        rating: int = Field(ge=1, le=5, description="How good it was")
        either: int | str = 0

    [rating] = score_configs(Review)
    assert (rating.name, rating.type_name, rating.field) == ("review.rating", "review", "rating")
    assert (rating.data_type, rating.minimum, rating.maximum) == ("NUMERIC", 1.0, 5.0)
    assert rating.description == "How good it was"
    assert score_configs(Review, type_name="code_review")[0].name == "code_review.rating"


def test_configs_keep_bounds_as_declared() -> None:
    class Effort(BaseModel):
        hours: int = Field(gt=0, lt=10)

    [hours] = score_configs(Effort)
    assert (hours.minimum, hours.maximum) == (0.0, 10.0)


def test_a_literal_of_enum_members_has_their_values_as_categories() -> None:
    class Mood(BaseModel):
        tone: Literal[Tone.WARM, Tone.COLD]

    [tone] = score_configs(Mood)
    assert tone.categories == ("warm", "cold")
    assert score_values(Mood, Mood(tone=Tone.COLD).model_dump(mode="json"))[0][1] == "cold"


def test_feedback_scores_have_a_source_and_no_evaluator() -> None:
    feedback = Score(
        id="f",
        name="helpfulness.rating",
        value=4.0,
        data_type="NUMERIC",
        session_id="thread-1",
        timestamp=datetime(2026, 9, 29, tzinfo=UTC),
        source={"tenant_id": "acme", "actor": "alice"},
    )
    assert feedback.metadata == {"tenant_id": "acme", "actor": "alice"}
    judged = scores(verdict())[0].model_copy(update={"source": {"run": "r1"}})
    assert judged.metadata == {
        "run": "r1",
        "evaluator": "judge",
        "version": "v1",
        "confidence": 0.9,
    }


def test_a_scores_timestamp_needs_a_time_zone() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        Score(id="f", name="a.b", value=1.0, data_type="NUMERIC", timestamp=datetime(2026, 9, 29))
