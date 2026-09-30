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


def test_long_text_is_cut() -> None:
    [note] = [s for s in scores(verdict(note="x" * (MAX_TEXT + 1))) if s.data_type == "TEXT"]
    assert note.value == "x" * MAX_TEXT


def test_values_may_be_a_models_fields_or_its_json() -> None:
    value = verdict().value
    from_fields = score_values(TaskCompletion, dict(value))
    from_json = score_values(TaskCompletion, value.model_dump(mode="json"))
    assert from_fields == from_json
    assert [v for _, v in from_json] == [True, 0.5, 3.0, "warm", "2", "fine"]
    assert score_values(TaskCompletion, {"steps": 4}) == [(score_configs(TaskCompletion)[2], 4.0)]


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


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"data_type": "BOOLEAN", "value": 1.0}, "a BOOLEAN score's value is a bool, not 1.0"),
        ({"data_type": "NUMERIC", "value": True}, "a NUMERIC score's value is a float, not True"),
        ({"data_type": "CATEGORICAL", "value": 2.0}, "a CATEGORICAL score's value is a str"),
        ({"data_type": "TEXT", "value": False}, "a TEXT score's value is a str"),
        ({"source": {"version": "2", "actor": "alice"}}, r"clash .*\['version'\]"),
        ({"span_id": "00f067aa0ba902b7"}, "needs a trace"),
    ],
    ids=["boolean", "numeric", "categorical", "text", "source", "span"],
)
def test_a_score_refuses_what_does_not_fit_together(
    fields: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        Score.model_validate(
            {"id": "s", "name": "a.b", "value": 1.0, "data_type": "NUMERIC"} | fields
        )
