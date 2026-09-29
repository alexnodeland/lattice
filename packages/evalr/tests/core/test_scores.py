import uuid
from enum import Enum
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from evalr import Verdict, scores
from evalr.core import SCORE_NAMESPACE, score_type_name

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
